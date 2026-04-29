from fastapi import HTTPException, status


class LinkNotFound(HTTPException):
    def __init__(self, shortcode: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "link_not_found", "shortcode": shortcode},
        )


class ShortcodeConflict(HTTPException):
    def __init__(self, shortcode: str):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "shortcode_already_exists", "shortcode": shortcode},
        )


class LinkExpired(HTTPException):
    def __init__(self, shortcode: str):
        super().__init__(
            status_code=status.HTTP_410_GONE,
            detail={"error": "link_expired", "shortcode": shortcode},
        )


class LinkInactive(HTTPException):
    def __init__(self, shortcode: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "link_inactive", "shortcode": shortcode},
        )