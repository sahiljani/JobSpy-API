from fastapi import HTTPException, status


def api_http_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            'code': code,
            'message': message,
        },
    )


def bad_request(message: str, code: str = 'bad_request') -> HTTPException:
    return api_http_error(status.HTTP_400_BAD_REQUEST, code, message)


def unauthorized(message: str = 'invalid API key', code: str = 'unauthorized') -> HTTPException:
    return api_http_error(status.HTTP_401_UNAUTHORIZED, code, message)


def not_found(message: str = 'resource not found', code: str = 'not_found') -> HTTPException:
    return api_http_error(status.HTTP_404_NOT_FOUND, code, message)


def conflict(message: str, code: str = 'conflict') -> HTTPException:
    return api_http_error(status.HTTP_409_CONFLICT, code, message)
