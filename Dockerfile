# Python 3.12 is the project's runtime (DESIGN SS5); the system Python on the
# dev Mac is 3.9 and is deliberately not used. Running in this image is what
# keeps the dev box and the deploy box on the same interpreter.
FROM python:3.12-slim

WORKDIR /app

# Install deps first, off the manifest alone, so a code change does not bust the
# pip layer cache. README.md is copied because pyproject names it as the readme.
COPY pyproject.toml README.md ./
COPY trmnl ./trmnl
RUN pip install --no-cache-dir -e ".[test]"

COPY tests ./tests

# The one test command (DESIGN SS5). --color=no keeps ANSI out even if some
# environment forces it; -q keeps the summary to a line of dots.
CMD ["python", "-m", "pytest", "-q", "--color=no"]
