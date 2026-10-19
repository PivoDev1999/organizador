from typing import Annotated

from pydantic import AfterValidator

from app.core.text import check_db_text, check_utf8, parse_email

# Valid UTF-8 (no lone surrogates). For text that never reaches the database, such as passwords.
Utf8Str = Annotated[str, AfterValidator(check_utf8)]
# Text safe to store in Postgres: valid UTF-8 and no NUL. Use it for every stored string field.
DbText = Annotated[str, AfterValidator(check_db_text)]
# Trimmed, lower-case and validated e-mail address.
Email = Annotated[str, AfterValidator(parse_email)]
