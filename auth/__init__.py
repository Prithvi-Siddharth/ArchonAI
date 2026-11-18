"""User accounts and JWT authentication for the ArchonAI API.

Registration and login issue a signed JWT in an HttpOnly cookie
(auth/tokens.py); routes that need a signed-in user depend on
auth.dependencies.get_current_user.
"""
