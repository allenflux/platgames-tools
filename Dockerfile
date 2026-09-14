FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY vendor_debug_server.py vendor_debug_tokens.py make_panda_natural_free_token.py panda_jwt.py ./
COPY vendor_debug_web/ ./vendor_debug_web/

EXPOSE 9100

CMD ["python3", "vendor_debug_server.py", "--host", "0.0.0.0", "--port", "9100"]
