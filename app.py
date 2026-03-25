import json
import os
import re

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate
from werkzeug.utils import secure_filename

from src.database import (
    User,
    clear_chat_history,
    delete_api_key,
    delete_document,
    get_active_provider,
    get_all_documents,
    get_api_key,
    get_chat_history,
    get_document_by_id,
    init_db,
    list_api_keys,
    log_admin_action,
    save_api_key,
    save_chat_history,
    save_document_metadata,
    set_active_provider,
    update_document,
)
from src.encryption import init_encryption
from src.helper import download_hugging_face_embeddings
from src.llm_factory import get_llm_factory
from src.llm_factory import validate_api_key as llm_validate_api_key
from src.logging_config import metrics, setup_logging
from src.prompt import system_prompt

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("FLASK_ENV") == "production"

# Initialise encryption with the app's secret key so all API keys stored in DB
# are encrypted/decrypted consistently with this key.
init_encryption(app.config["SECRET_KEY"])

setup_logging(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# Rate limiter — 20 chat requests/minute per IP, 200/day overall
# Uses Redis when REDIS_URL is set (Docker/production), in-memory otherwise (dev/test)
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri=os.getenv("REDIS_URL", "memory://"),
)

init_db()

load_dotenv()

embeddings = download_hugging_face_embeddings()

docsearch = None
retriever = None


def _load_faiss_index():
    """Load (or hot-reload) the FAISS index into the module-level globals."""
    global docsearch, retriever
    try:
        docsearch = FAISS.load_local("faiss_index", embeddings, allow_dangerous_deserialization=True)
        retriever = docsearch.as_retriever(search_type="similarity", search_kwargs={"k": 3})
        app.logger.info("FAISS index loaded successfully")
    except Exception as _err:
        app.logger.warning(f"FAISS index not loaded: {_err}. Run store_index.py to build it.")
        docsearch = None
        retriever = None


_load_faiss_index()

# LLM is loaded dynamically per-request so switching providers in the dashboard
# takes effect immediately without restarting the server.
_llm_cache = {"provider": None, "llm": None}


def get_active_llm():
    """Return the current LLM, reloading if the active provider has changed."""
    active = get_active_provider()
    provider = active["provider"] if active else "gemini"
    if _llm_cache["provider"] != provider or _llm_cache["llm"] is None:
        _llm_cache["llm"] = get_llm_factory().get_llm()
        _llm_cache["provider"] = provider
    return _llm_cache["llm"]


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", system_prompt),
        ("human", "{input}"),
    ]
)


@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)


@app.after_request
def set_security_headers(response):
    """Apply security headers to every Flask response (belt-and-suspenders with nginx)."""
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-XSS-Protection", "1; mode=block")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    # 'unsafe-inline' required while templates use inline <script> / <style> blocks.
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:;",
    )
    return response


@app.route("/")
@login_required
def index():
    active = get_active_provider()
    provider_name = active["provider"].capitalize() if active else "Gemini"
    return render_template("chat.html", username=current_user.username, active_provider=provider_name)


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            return render_template("login.html", error="Username and password are required")

        if User.verify_password(username, password):
            user = User.get_by_username(username)
            login_user(user)
            # Regenerate session to prevent session fixation
            session.permanent = True
            return redirect(url_for("index"))
        else:
            app.logger.warning("Failed login attempt", extra={"username": username[:30], "ip": request.remote_addr})
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        # Username: 3-30 chars, letters/numbers/underscores/hyphens only
        if not re.match(r"^[a-zA-Z0-9_-]{3,30}$", username):
            return render_template(
                "signup.html",
                error="Username must be 3-30 characters and contain only letters, numbers, underscores or hyphens",
            )

        # Basic email sanity check
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return render_template("signup.html", error="Please enter a valid email address")

        if password != confirm_password:
            return render_template("signup.html", error="Passwords do not match")

        if len(password) < 8:
            return render_template("signup.html", error="Password must be at least 8 characters")
        if not re.search(r"[A-Z]", password):
            return render_template("signup.html", error="Password must contain at least one uppercase letter")
        if not re.search(r"\d", password):
            return render_template("signup.html", error="Password must contain at least one number")

        user = User.create(username, email, password)
        if user:
            return render_template("login.html", success="Account created successfully! Please login.")
        else:
            return render_template("signup.html", error="Username or email already exists")

    return render_template("signup.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/history")
@login_required
def history():
    chat_history = get_chat_history(current_user.id)
    return jsonify({"history": chat_history})


@app.route("/metrics")
@login_required
def metrics_dashboard():
    return render_template("metrics.html", metrics=metrics.get_metrics())


@app.route("/api/metrics")
@login_required
def api_metrics():
    """JSON endpoint for metrics (for external monitoring tools)"""
    return jsonify(metrics.get_metrics())


@app.route("/health")
def health():
    """Lightweight health check used by CI/CD deploy scripts and load balancers."""
    return jsonify({"status": "ok", "index_loaded": retriever is not None})


# Emergency keywords detection
EMERGENCY_KEYWORDS = [
    "emergency",
    "911",
    "urgent",
    "heart attack",
    "stroke",
    "chest pain",
    "can't breathe",
    "cannot breathe",
    "difficulty breathing",
    "choking",
    "severe bleeding",
    "heavy bleeding",
    "unconscious",
    "passed out",
    "suicide",
    "suicidal",
    "kill myself",
    "overdose",
    "seizure",
    "severe pain",
    "broken bone",
    "head injury",
    "allergic reaction",
]


def detect_emergency(text):
    """Detect if the message contains emergency keywords."""
    text_lower = text.lower()
    for keyword in EMERGENCY_KEYWORDS:
        if keyword in text_lower:
            return True
    return False


def validate_input(text):
    """Validate user input to prevent prompt injection and ensure quality."""
    if not text or not text.strip():
        return False, "Please enter a question."

    if len(text) > 2000:
        return False, "Question is too long. Please keep it under 2000 characters."

    # Check for potential prompt injection patterns
    injection_patterns = [
        r"ignore\s+(previous|above|all)\s+instructions",
        r"system\s*:\s*you\s+are",
        r"<\s*script\s*>",
        r"DROP\s+TABLE",
        r"DELETE\s+FROM",
    ]

    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return False, "Invalid input detected. Please ask a genuine medical question."

    return True, None


def get_user_conversation_memory():
    """Get or create conversation memory for the current user session."""
    if "conversation_history" not in session:
        session["conversation_history"] = []
    return session["conversation_history"]


def add_to_conversation_memory(question, answer):
    """Add Q&A pair to user's conversation memory."""
    if "conversation_history" not in session:
        session["conversation_history"] = []

    session["conversation_history"].append({"question": question, "answer": answer})

    # Keep only last 5 exchanges to avoid token limits
    if len(session["conversation_history"]) > 5:
        session["conversation_history"] = session["conversation_history"][-5:]

    session.modified = True


def calculate_response_confidence(retrieved_docs, question):
    """Calculate confidence score for the retrieved documents."""
    if not retrieved_docs:
        return 0.0, "No relevant information found."

    # Simple confidence based on number of documents and similarity
    # In production, you'd use actual similarity scores from the retriever
    num_docs = len(retrieved_docs)

    if num_docs >= 3:
        confidence = 0.8
        message = None
    elif num_docs == 2:
        confidence = 0.6
        message = "Limited information available. Consider consulting a healthcare professional for more details."
    else:
        confidence = 0.4
        message = "Very limited information found. Please consult a healthcare professional."

    return confidence, message


@app.route("/get", methods=["POST"])
@login_required
@limiter.limit("20 per minute; 200 per day")
def chat():
    try:
        msg = request.form.get("msg", "")

        # Validate input
        is_valid, error_msg = validate_input(msg)
        if not is_valid:
            app.logger.warning(f"Invalid input: {error_msg}", extra={"user_id": current_user.id})
            return Response(
                f"data: {json.dumps({'token': error_msg, 'error': True})}\n\n"
                + f"data: {json.dumps({'done': True})}\n\n",
                mimetype="text/event-stream",
            )

        # Check for emergency
        if detect_emergency(msg):
            app.logger.warning(f"Emergency detected: {msg}", extra={"user_id": current_user.id})
            emergency_response = """🚨 EMERGENCY DETECTED 🚨

If you are experiencing a medical emergency, please:

1. Call 911 (US) or your local emergency number IMMEDIATELY
2. Do not rely on this chatbot for emergency medical advice
3. Seek professional emergency medical care right away

Examples of medical emergencies include:
• Chest pain or pressure
• Difficulty breathing
• Severe bleeding
• Loss of consciousness
• Stroke symptoms (face drooping, arm weakness, speech difficulty)
• Severe allergic reactions
• Suicidal thoughts

This chatbot cannot provide emergency medical assistance. Please contact emergency services now."""

            return Response(
                f"data: {json.dumps({'token': emergency_response})}\n\n"
                + f"data: {json.dumps({'done': True, 'emergency': True})}\n\n",
                mimetype="text/event-stream",
            )

        app.logger.info(f"Question received: {msg}", extra={"user_id": current_user.id})

        # Get conversation history for context
        conversation_history = get_user_conversation_memory()
        context_messages = ""
        if conversation_history:
            context_messages = "\n\nPrevious conversation context:\n"
            for i, exchange in enumerate(conversation_history[-3:], 1):  # Last 3 exchanges
                context_messages += f"Q{i}: {exchange['question']}\nA{i}: {exchange['answer'][:200]}...\n"

        full_response = []
        sources = []

        def generate():
            try:
                if retriever is None:
                    error_msg = "Knowledge base index not ready. Please ask an admin to run store_index.py."
                    yield f"data: {json.dumps({'token': error_msg, 'error': True})}\n\n"
                    yield f"data: {json.dumps({'done': True})}\n\n"
                    return

                # Retrieve relevant documents
                retrieved_docs = retriever.invoke(msg)

                # Calculate confidence
                confidence, warning_message = calculate_response_confidence(retrieved_docs, msg)

                # Extract sources
                for doc in retrieved_docs:
                    source_info = {
                        "content": doc.page_content[:200],
                        "metadata": doc.metadata if hasattr(doc, "metadata") else {},
                    }
                    sources.append(source_info)

                # Check if we have enough information
                if confidence < 0.5:
                    token_data = {"token": warning_message or "Insufficient information available."}
                    yield f"data: {json.dumps(token_data)}\n\n"
                    token_data = {"token": " Please consult a professional for accurate information."}
                    yield f"data: {json.dumps(token_data)}\n\n"
                    done_data = {"done": True, "confidence": confidence}
                    yield f"data: {json.dumps(done_data)}\n\n"
                    return

                # Format the context with conversation history
                context = context_messages + "\n\n" + "\n\n".join([doc.page_content for doc in retrieved_docs])

                # Create the full prompt with context
                formatted_prompt = prompt.format_messages(context=context, input=msg)

                # Stream the response from the LLM (uses whichever provider is active)
                for chunk in get_active_llm().stream(formatted_prompt):
                    if hasattr(chunk, "content") and chunk.content:
                        full_response.append(chunk.content)
                        yield f"data: {json.dumps({'token': chunk.content})}\n\n"

                # Add disclaimer
                disclaimer = (
                    "\n\n⚠️ Medical Disclaimer: This information is for educational purposes only "
                    "and should not replace professional medical advice, diagnosis, or treatment. "
                    "Always consult with a qualified healthcare provider for medical decisions."
                )
                yield f"data: {json.dumps({'token': disclaimer})}\n\n"

                # Add low confidence warning if needed
                if warning_message and confidence < 0.8:
                    warning_text = f"\n\nℹ️ {warning_message}"
                    yield f"data: {json.dumps({'token': warning_text})}\n\n"

                # Add sources
                if sources:
                    sources_text = "\n\n📚 Sources:\n"
                    for i, source in enumerate(sources[:3], 1):
                        metadata = source.get("metadata", {})
                        source_name = metadata.get("source", "Medical Document")
                        page = metadata.get("page", "N/A")
                        sources_text += f"• {source_name} (Page {page})\n"
                    yield f"data: {json.dumps({'token': sources_text})}\n\n"

                # Send completion signal with metadata
                yield f"data: {json.dumps({'done': True, 'confidence': confidence, 'sources': sources[:3]})}\n\n"

                # Save to conversation memory and chat history
                answer = "".join(full_response)
                add_to_conversation_memory(msg, answer)
                save_chat_history(current_user.id, msg, answer)

                app.logger.info(
                    "Response generated successfully",
                    extra={
                        "user_id": current_user.id,
                        "response_length": len(answer),
                        "confidence": confidence,
                        "sources_count": len(sources),
                    },
                )

            except Exception as e:
                app.logger.error(f"Streaming Error: {e}", extra={"user_id": current_user.id}, exc_info=True)

                # Determine error type and provide specific message
                if "API" in str(e) or "quota" in str(e).lower():
                    error_msg = "Sorry, the AI service is currently unavailable. Please try again later."
                elif "timeout" in str(e).lower():
                    error_msg = "The request timed out. Please try with a shorter question."
                else:
                    error_msg = "Sorry, I encountered an error processing your question. Please try again."

                yield f"data: {json.dumps({'token': error_msg, 'error': True})}\n\n"
                yield f"data: {json.dumps({'done': True})}\n\n"

        return Response(stream_with_context(generate()), mimetype="text/event-stream")

    except Exception as e:
        app.logger.error(f"Chat route error: {e}", exc_info=True)
        return Response(
            f"data: {json.dumps({'token': 'Sorry, I encountered an error. Please try again.', 'error': True})}\n\n"
            + f"data: {json.dumps({'done': True})}\n\n",
            mimetype="text/event-stream",
        )


@app.route("/clear-history", methods=["POST"])
@login_required
def clear_history():
    """Clear conversation history for the current user session and database."""
    try:
        # Clear session conversation history
        session["conversation_history"] = []
        session.modified = True

        # Clear database chat history
        if clear_chat_history(current_user.id):
            return jsonify({"success": True, "message": "Conversation history cleared"})
        else:
            return jsonify({"success": False, "message": "Failed to clear database history"}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500


@app.route("/admin")
@login_required
def admin_panel():
    """Admin interface for managing knowledge base."""
    if not current_user.is_admin:
        return "Access denied. Admin privileges required.", 403
    return render_template("admin.html")


@app.route("/admin/upload", methods=["POST"])
@login_required
def admin_upload():
    """Upload new PDF to knowledge base."""
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    try:
        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]

        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400

        if not file.filename.lower().endswith(".pdf"):
            return jsonify({"error": "Only PDF files are allowed"}), 400

        # Sanitise filename to prevent path traversal (e.g. "../../../etc/passwd")
        safe_name = secure_filename(file.filename)
        if not safe_name:
            return jsonify({"error": "Invalid filename"}), 400

        filename = os.path.join("Data", safe_name)
        file.save(filename)

        # Count pages for metadata
        page_count = 0
        try:
            import pypdf

            reader = pypdf.PdfReader(filename)
            page_count = len(reader.pages)
        except Exception:
            try:
                import PyPDF2

                with open(filename, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    page_count = len(reader.pages)
            except Exception:
                pass

        # Track document in database
        save_document_metadata(
            filename=safe_name,
            original_name=file.filename,
            file_path=filename,
            file_size=os.path.getsize(filename),
            page_count=page_count,
        )

        app.logger.info(f"PDF uploaded: {safe_name}", extra={"user_id": current_user.id})

        return jsonify(
            {
                "success": True,
                "filename": safe_name,
                "message": "File uploaded successfully. Re-index to make it searchable.",
            }
        )

    except Exception as e:
        app.logger.error(f"Upload error: {e}", exc_info=True)
        return jsonify({"error": "File upload failed. Please try again."}), 500


@app.route("/admin/reindex", methods=["POST"])
@login_required
def admin_reindex():
    """Trigger FAISS index rebuild."""
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403

    try:
        import subprocess

        # Run store_index.py in background
        result = subprocess.run(
            ["python", "store_index.py"], capture_output=True, text=True, timeout=300  # 5 minute timeout
        )

        if result.returncode == 0:
            app.logger.info(
                "Index rebuilt successfully", extra={"user_id": current_user.id, "output_preview": result.stdout[:500]}
            )
            for doc in get_all_documents(active_only=False):
                if doc.get("id"):
                    update_document(doc["id"], status="indexed")
            _load_faiss_index()
            return jsonify({"success": True, "message": "Index rebuilt and reloaded successfully"})
        else:
            app.logger.error(f"Index rebuild failed: {result.stderr[:500]}")
            return jsonify({"error": "Index rebuild failed. Check server logs for details."}), 500

    except subprocess.TimeoutExpired:
        return jsonify({"error": "Indexing timed out (>5 minutes)"}), 500
    except Exception as e:
        app.logger.error(f"Reindex error: {e}", exc_info=True)
        return jsonify({"error": "Reindex failed. Check server logs for details."}), 500


@app.route("/dashboard")
@login_required
def dashboard():
    """Admin dashboard for managing API keys and documents."""
    if not current_user.is_admin:
        return "Access denied. Admin privileges required.", 403
    return render_template("dashboard.html", username=current_user.username)


# ── Dashboard API: keys ────────────────────────────────────────────────────


@app.route("/dashboard/api/keys", methods=["GET"])
@login_required
def dashboard_list_keys():
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    keys = list_api_keys(show_keys=True)
    active = get_active_provider()
    active_provider = active["provider"] if active else None
    return jsonify({"keys": keys, "active_provider": active_provider})


@app.route("/dashboard/api/keys", methods=["POST"])
@login_required
def dashboard_save_key():
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json()
    provider = data.get("provider", "").strip().lower()
    api_key = data.get("api_key", "").strip()
    if provider not in ("gemini", "openai", "claude"):
        return jsonify({"error": "Invalid provider"}), 400
    if not api_key:
        return jsonify({"error": "API key is required"}), 400
    success = save_api_key(provider, api_key)
    if success:
        log_admin_action(current_user.id, "save_api_key", f"provider={provider}", request.remote_addr)
        return jsonify({"success": True, "message": f"{provider.capitalize()} key saved"})
    return jsonify({"error": "Failed to save key"}), 500


@app.route("/dashboard/api/keys/<provider>", methods=["DELETE"])
@login_required
def dashboard_delete_key(provider):
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    if provider not in ("gemini", "openai", "claude"):
        return jsonify({"error": "Invalid provider"}), 400
    success = delete_api_key(provider)
    if success:
        log_admin_action(current_user.id, "delete_api_key", f"provider={provider}", request.remote_addr)
        return jsonify({"success": True})
    return jsonify({"error": "Failed to delete key"}), 500


@app.route("/dashboard/api/keys/<provider>/activate", methods=["POST"])
@login_required
def dashboard_activate_key(provider):
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    if provider not in ("gemini", "openai", "claude"):
        return jsonify({"error": "Invalid provider"}), 400
    existing = get_api_key(provider)
    if not existing:
        return jsonify({"error": f"No key saved for {provider}"}), 400
    success = set_active_provider(provider)
    if success:
        log_admin_action(current_user.id, "activate_provider", f"provider={provider}", request.remote_addr)
        return jsonify({"success": True, "message": f"{provider.capitalize()} is now active"})
    return jsonify({"error": "Failed to set active provider"}), 500


@app.route("/dashboard/api/keys/validate", methods=["POST"])
@login_required
def dashboard_validate_key():
    """Test whether a given API key actually works for its provider."""
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    data = request.get_json()
    provider = data.get("provider", "").strip().lower()
    api_key = data.get("api_key", "").strip()
    if provider not in ("gemini", "openai", "claude"):
        return jsonify({"error": "Invalid provider"}), 400
    # If no key supplied in body, fall back to the saved key
    if not api_key:
        api_key = get_api_key(provider)
        if not api_key:
            return jsonify({"valid": False, "message": f"No key saved for {provider}"}), 400
    result = llm_validate_api_key(provider, api_key)
    return jsonify(result)


# ── Dashboard API: documents ───────────────────────────────────────────────


@app.route("/dashboard/api/documents", methods=["GET"])
@login_required
def dashboard_list_docs():
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    db_docs = {d["filename"]: d for d in get_all_documents()}
    disk_files = []
    data_dir = "Data"
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            if fname.lower().endswith(".pdf"):
                fpath = os.path.join(data_dir, fname)
                size = os.path.getsize(fpath)
                if fname in db_docs:
                    db_docs[fname]["on_disk"] = True
                else:
                    disk_files.append(
                        {
                            "id": None,
                            "filename": fname,
                            "original_name": fname,
                            "file_path": fpath,
                            "file_size": size,
                            "page_count": 0,
                            "is_active": True,
                            "status": "untracked",
                            "on_disk": True,
                            "created_at": None,
                        }
                    )
    docs = list(db_docs.values()) + disk_files
    for d in docs:
        if "on_disk" not in d:
            d["on_disk"] = os.path.exists(d.get("file_path", ""))
    return jsonify({"documents": docs})


@app.route("/dashboard/api/documents/<int:doc_id>/toggle", methods=["POST"])
@login_required
def dashboard_toggle_doc(doc_id):
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    doc = get_document_by_id(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    new_state = not doc["is_active"]
    update_document(doc_id, is_active=int(new_state))
    return jsonify({"success": True, "is_active": new_state})


@app.route("/dashboard/api/documents/<int:doc_id>", methods=["DELETE"])
@login_required
def dashboard_delete_doc(doc_id):
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    doc = get_document_by_id(doc_id)
    if not doc:
        return jsonify({"error": "Document not found"}), 404
    remove_file = request.args.get("remove_file", "false").lower() == "true"
    if remove_file and doc.get("file_path") and os.path.exists(doc["file_path"]):
        try:
            os.remove(doc["file_path"])
        except OSError as e:
            app.logger.warning(f"Could not delete file {doc['file_path']}: {e}")
    delete_document(doc_id)
    log_admin_action(current_user.id, "delete_document", f"filename={doc['filename']}", request.remote_addr)
    return jsonify({"success": True})


@app.route("/dashboard/api/stats", methods=["GET"])
@login_required
def dashboard_stats():
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    data_dir = "Data"
    pdf_count = 0
    if os.path.isdir(data_dir):
        pdf_count = sum(1 for f in os.listdir(data_dir) if f.lower().endswith(".pdf"))
    index_exists = os.path.isdir("faiss_index") and bool(os.listdir("faiss_index"))
    active = get_active_provider()
    return jsonify(
        {
            "pdf_count": pdf_count,
            "index_exists": index_exists,
            "active_provider": active["provider"] if active else "env/default",
        }
    )


# Also expose /admin/stats for the legacy admin.html
@app.route("/admin/stats", methods=["GET"])
@login_required
def admin_stats():
    if not current_user.is_admin:
        return jsonify({"error": "Access denied"}), 403
    data_dir = "Data"
    pdf_count = sum(1 for f in os.listdir(data_dir) if f.lower().endswith(".pdf")) if os.path.isdir(data_dir) else 0
    index_exists = os.path.isdir("faiss_index") and bool(os.listdir("faiss_index"))
    return jsonify({"pdf_count": pdf_count, "index_exists": index_exists})


if __name__ == "__main__":
    # debug=True exposes the Werkzeug interactive shell (RCE risk).
    # Never run with debug=True in production — use gunicorn instead.
    debug_mode = os.getenv("FLASK_ENV", "production") == "development"
    app.run(host="0.0.0.0", port=8080, debug=debug_mode)  # nosec B104
