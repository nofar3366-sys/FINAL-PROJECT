"""Vercel / local WSGI entrypoint.

Vercel Serverless Functions import this module and look for a global `app`.
"""

from fitness_studio import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
