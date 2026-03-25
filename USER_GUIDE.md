# User Guide

Welcome to the Medical Chatbot — a RAG-powered medical Q&A assistant that answers questions based on your knowledge base of medical PDFs, with real-time streaming responses.

> **Medical Disclaimer**: This chatbot provides general educational information only. It is **not** a substitute for professional medical advice, diagnosis, or treatment. Always consult a qualified healthcare provider.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Chat Interface](#chat-interface)
3. [How to Ask Questions](#how-to-ask-questions)
4. [Understanding Responses](#understanding-responses)
5. [Admin Dashboard](#admin-dashboard)
6. [Safety Features](#safety-features)
7. [FAQ](#faq)

---

## Getting Started

### Creating an Account

1. Visit the Medical Chatbot website and click **Sign Up**
2. Choose a username (3–30 characters, letters/numbers/`_`/`-` only)
3. Enter a valid email address
4. Choose a strong password:
   - At least **8 characters**
   - At least **1 uppercase letter**
   - At least **1 number**
5. Confirm your password and click **Create Account**
6. Log in with your credentials

### First Conversation

1. After logging in, you'll see the chat interface with your previous conversation history (if any) loaded automatically
2. Type your medical question in the text box at the bottom
3. Press **Enter** or click the send button
4. Tokens stream in as the AI generates the response — no need to wait for the full answer
5. Read the answer and the source citations at the bottom of each response

---

## Chat Interface

### What you see

- **Chat history** — your last 50 exchanges load automatically when you open the page; no need to scroll back through previous sessions
- **Streaming responses** — text appears word-by-word as the LLM generates it
- **Source citations** — every answer shows which PDF and page the information came from
- **Confidence warnings** — if the retrieved documents don't closely match your question, a warning recommends consulting a professional

### Character limit

Messages are limited to **2000 characters**. For complex multi-part questions, split them into separate messages.

### Clearing history

Click **Clear History** to wipe your conversation from both the current session and the database. This action is permanent.

---

## How to Ask Questions

### Good questions

The chatbot works best with clear, specific questions about medical topics covered by the loaded PDFs.

```
✅ "What are the symptoms of Type 2 diabetes?"
✅ "How does insulin work in the human body?"
✅ "What causes high blood pressure?"
✅ "Explain the difference between arteries and veins"
✅ "What medications are used for hypertension?"
```

### Questions to avoid

```
❌ "Am I sick?" — cannot diagnose based on a text conversation
❌ "What medicine should I take?" — requires professional evaluation
❌ "Is my X-ray normal?" — cannot interpret images
❌ Very vague questions like "Tell me about health"
```

### Tips for better answers

- **Be specific**: "What are the early signs of Type 1 diabetes in children?" gets a better answer than "Tell me about diabetes"
- **One topic per message**: Complex multi-topic questions reduce retrieval accuracy
- **Use medical terms when you know them**: The knowledge base is indexed from medical literature

---

## Understanding Responses

### Source citations

Every response includes citations like:

```
Source: clinical_guide.pdf (page 42)
```

Citations show exactly which document and page the information came from. Use these to verify answers against the original source.

### Confidence indicator

When the retrieved documents don't closely match your question, you'll see:

> ⚠️ Low confidence — I recommend consulting a qualified medical professional for this query.

This means the question may be outside the scope of the loaded knowledge base.

### Emergency detection

If your message contains emergency keywords (chest pain, difficulty breathing, stroke symptoms, etc.), the chatbot bypasses the LLM entirely and immediately returns:

> 🚨 EMERGENCY DETECTED. If this is a medical emergency, call 911 immediately...

This response is instantaneous and does not depend on API availability.

---

## Admin Dashboard

The dashboard (`/dashboard`) is available to admin users only.

### API Keys tab

Manage which LLM powers the chatbot:

1. Navigate to **Dashboard → API Keys**
2. Paste your API key for Gemini, OpenAI, or Claude
3. Click **Test Key** — this fires a real API call to validate the key before saving
4. Click **Save**
5. Click **Set as Active** to switch the live LLM

The switch takes effect on the **next chat request** — no server restart needed. The full API key is never shown; only the last 4 characters are displayed.

Supported providers:
- **Gemini** (`gemini-2.5-flash`) — recommended default
- **OpenAI** (`gpt-4o`)
- **Claude** (`claude-opus-4-6`)

### Documents tab

Manage the knowledge base:

| Action | Effect |
|--------|--------|
| **Upload PDF** | Drag-and-drop or click to upload; file appears with status `pending_index` |
| **Enable / Disable** | Toggles whether the document is included in retrieval |
| **Rebuild Index** | Runs `store_index.py` and hot-reloads FAISS — no restart needed; documents update to `indexed` |
| **Delete** | Remove from database; optionally delete file from disk |

After uploading new PDFs, always click **Rebuild Index** to make them searchable.

---

## Safety Features

### Rate limits

To prevent abuse, the following limits apply per IP address:

| Endpoint | Limit |
|----------|-------|
| Chat (`/get`) | 20 per minute · 200 per day |
| Login | 10 per minute |
| Sign up | 5 per minute |

If you hit a rate limit, you'll receive a `429 Too Many Requests` response. Wait 1 minute before retrying.

### Input filtering

The following are rejected with an error message (not sent to the LLM):
- Messages over 2000 characters
- Prompt injection patterns (`ignore previous instructions`, `system: you are`, etc.)
- SQL injection patterns (`DROP TABLE`, `DELETE FROM`)
- Script tags

---

## FAQ

**Q: Why does the chatbot say it doesn't know the answer?**
The answer is likely outside the PDFs loaded into the knowledge base. Ask an admin to upload the relevant document and rebuild the index.

**Q: The response looks cut off — is that normal?**
Each provider has a token limit per response. For very detailed questions, ask a follow-up to get more detail.

**Q: My previous conversations aren't showing.**
History loads automatically on page open. If nothing appears, you may not have any prior history, or the database may have been reset. Click "Clear History" and start fresh.

**Q: I keep getting rate limit errors.**
Wait 1 minute. If you're a developer, set `FLASK_ENV=development` to increase limits during local testing.

**Q: Who can access the admin dashboard?**
Only users with the `is_admin` flag set in the database. Contact your system administrator to request access.

**Q: Is my chat history private?**
Yes — history is stored per user and only accessible to you. Admins can access the database directly but cannot see your history through the chat interface.

**Q: How do I change my password?**
There is currently no self-service password reset. Contact your system administrator.
