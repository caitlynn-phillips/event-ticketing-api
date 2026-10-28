def assert_error_schema(response, code, status_code):
    """Check a response uses the standard error schema; return the error dict."""
    body = response.json()
    assert response.status_code == status_code
    assert set(body.keys()) == {"error"}
    error = body["error"]
    assert error["code"] == code
    assert error["status"] == status_code
    assert isinstance(error["message"], str)
    assert "details" in error
    return error
