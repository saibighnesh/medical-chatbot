import logging
import json
from datetime import datetime
from functools import wraps
import time
from flask import request, g
from pythonjsonlogger import jsonlogger

class MetricsTracker:
    def __init__(self):
        self.reset_metrics()
    
    def reset_metrics(self):
        self.total_requests = 0
        self.total_errors = 0
        self.response_times = []
        self.endpoint_stats = {}
        self.start_time = datetime.now()
    
    def record_request(self, endpoint, response_time, status_code):
        self.total_requests += 1
        self.response_times.append(response_time)
        
        if status_code >= 400:
            self.total_errors += 1
        
        if endpoint not in self.endpoint_stats:
            self.endpoint_stats[endpoint] = {
                'count': 0,
                'total_time': 0,
                'errors': 0
            }
        
        self.endpoint_stats[endpoint]['count'] += 1
        self.endpoint_stats[endpoint]['total_time'] += response_time
        if status_code >= 400:
            self.endpoint_stats[endpoint]['errors'] += 1
    
    def get_metrics(self):
        uptime = (datetime.now() - self.start_time).total_seconds()
        avg_response_time = sum(self.response_times) / len(self.response_times) if self.response_times else 0
        error_rate = (self.total_errors / self.total_requests * 100) if self.total_requests > 0 else 0
        
        endpoint_metrics = {}
        for endpoint, stats in self.endpoint_stats.items():
            endpoint_metrics[endpoint] = {
                'count': stats['count'],
                'avg_response_time': stats['total_time'] / stats['count'] if stats['count'] > 0 else 0,
                'error_rate': (stats['errors'] / stats['count'] * 100) if stats['count'] > 0 else 0
            }
        
        return {
            'uptime_seconds': uptime,
            'total_requests': self.total_requests,
            'total_errors': self.total_errors,
            'error_rate_percent': error_rate,
            'avg_response_time_ms': avg_response_time * 1000,
            'endpoints': endpoint_metrics
        }

metrics = MetricsTracker()

def setup_logging(app):
    """Configure JSON structured logging"""
    
    # Create logs directory if it doesn't exist
    import os
    log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure JSON formatter
    logHandler = logging.FileHandler(os.path.join(log_dir, 'app.log'))
    formatter = jsonlogger.JsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s %(pathname)s %(lineno)d'
    )
    logHandler.setFormatter(formatter)
    
    # Console handler with JSON format
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(formatter)
    
    # Set up application logger
    app.logger.addHandler(logHandler)
    app.logger.addHandler(consoleHandler)
    app.logger.setLevel(logging.INFO)
    
    # Also configure root logger
    logging.getLogger().addHandler(logHandler)
    logging.getLogger().setLevel(logging.INFO)
    
    @app.before_request
    def before_request():
        g.start_time = time.time()
        app.logger.info('Request started', extra={
            'timestamp': datetime.utcnow().isoformat(),
            'method': request.method,
            'path': request.path,
            'ip': request.remote_addr,
            'user_agent': request.user_agent.string
        })
    
    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            response_time = time.time() - g.start_time
            metrics.record_request(request.endpoint, response_time, response.status_code)
            
            app.logger.info('Request completed', extra={
                'timestamp': datetime.utcnow().isoformat(),
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'response_time_ms': response_time * 1000,
                'endpoint': request.endpoint
            })
        return response
    
    @app.errorhandler(Exception)
    def handle_exception(e):
        from werkzeug.exceptions import HTTPException
        # Pass HTTP errors (404, 405, …) straight through — don't convert to 500
        if isinstance(e, HTTPException):
            return e
        app.logger.error('Unhandled exception', extra={
            'timestamp': datetime.utcnow().isoformat(),
            'error': str(e),
            'type': type(e).__name__,
            'path': request.path,
            'method': request.method
        }, exc_info=True)
        return {'error': 'Internal server error'}, 500
    
    return app

def log_action(action_type):
    """Decorator to log specific actions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            start_time = time.time()
            try:
                result = f(*args, **kwargs)
                duration = time.time() - start_time
                logging.info(f'{action_type} completed', extra={
                    'timestamp': datetime.utcnow().isoformat(),
                    'action': action_type,
                    'duration_ms': duration * 1000,
                    'success': True
                })
                return result
            except Exception as e:
                duration = time.time() - start_time
                logging.error(f'{action_type} failed', extra={
                    'timestamp': datetime.utcnow().isoformat(),
                    'action': action_type,
                    'duration_ms': duration * 1000,
                    'error': str(e),
                    'success': False
                }, exc_info=True)
                raise
        return decorated_function
    return decorator
