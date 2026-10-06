"""Turn a database connection failure into one actionable line.

Helper for the setup scripts, not a script itself. A wrong DATABASE_URL used to
surface as a ~200-line SQLAlchemy/PyMySQL traceback whose single useful line was
buried at the bottom, which is how MySQL error 1045 managed to look like a bug in
the schema loader rather than a missing .env.
"""

import sys

import sqlalchemy

# MySQL server error codes worth explaining rather than dumping.
ACCESS_DENIED = 1045
UNKNOWN_DATABASE = 1049
CONNECTION_REFUSED = 2003

HINTS = {
    ACCESS_DENIED: (
        "The credentials in DATABASE_URL were rejected.\n"
        "  If you have not created .env yet, that is the cause: app/config.py falls\n"
        "  back to a built-in default password ('change_me'), which will not match\n"
        "  the password you gave bootstrap_mysql.py.\n\n"
        "  Fix:  $env:MYSQL_PASSWORD = \"<the app password>\"\n"
        "        python scripts/bootstrap_mysql.py     # now writes .env for you"
    ),
    UNKNOWN_DATABASE: (
        "The database in DATABASE_URL does not exist.\n"
        "  Run:  python scripts/bootstrap_mysql.py"
    ),
    CONNECTION_REFUSED: (
        "Nothing is listening on that host/port.\n"
        "  Check the MySQL80 service is running and that the port is 3306:\n"
        "        Get-Service MySQL80"
    ),
}


def guarded(main) -> int:
    """Run `main`, reporting connection problems in one line instead of a traceback."""
    try:
        return main()
    except sqlalchemy.exc.OperationalError as exc:
        code = exc.orig.args[0] if getattr(exc, "orig", None) and exc.orig.args else None
        message = exc.orig.args[1] if getattr(exc, "orig", None) and len(exc.orig.args) > 1 else exc
        print(f"\nERROR: MySQL {code}: {message}\n", file=sys.stderr)
        hint = HINTS.get(code)
        if hint:
            print(f"  {hint}\n", file=sys.stderr)
        return 1
