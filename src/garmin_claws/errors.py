from __future__ import annotations


class ClawsError(Exception):
    def __init__(self, code: str, message: str, remediation: str, exit_code: int = 1):
        self.code = code
        self.message = message
        self.remediation = remediation
        self.exit_code = exit_code
        super().__init__(message)
