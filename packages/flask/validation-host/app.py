from flask import Flask, request
from markupsafe import escape

from s4_auth_flask import AuthConfig, S4Auth, current_user, public, require_role

config = AuthConfig.from_env()
app = Flask(__name__)
S4Auth(app, config)


def _page(body: str) -> str:
    return f"<!doctype html><title>s4-auth validation host</title><body>{body}</body>"


@app.get("/")
@public
def home():
    return _page('<h1>Validation host</h1><p><a href="/protected">Sign in</a></p>')


@app.get("/protected")
def protected():
    user = current_user()
    return _page(
        f"<h1>Signed in</h1>"
        f"<p>Email: {escape(user['email'])}</p>"
        f"<p>Roles: {escape(', '.join(user.get('roles') or [])) or '(none)'}</p>"
        f"<p>Session cookie name: {escape(config.cookie_name)}</p>"
        '<p><a href="/admin">/admin</a> | <a href="/auth/login">/auth/login</a></p>'
        '<form method="post" action="/auth/logout"><button>Log out</button></form>'
        '<form method="post" action="/echo"><button>POST /echo</button></form>'
    )


@app.get("/admin")
@require_role("s4-auth-validation")
def admin():
    return _page("<h1>Admin</h1><p>You hold the s4-auth-validation role.</p>")


@app.post("/echo")
def echo():
    return _page(f"<h1>POST accepted</h1><p>Method: {escape(request.method)}</p>")
