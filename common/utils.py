import uuid

def generate_uuid():
    return str(uuid.uuid4())

def idempotency_key(request):
    return request.headers.get("Idempotency-Key", generate_uuid())
