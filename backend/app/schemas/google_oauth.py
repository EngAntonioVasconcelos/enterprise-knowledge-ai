from pydantic import BaseModel, ConfigDict, Field


class GoogleAuthorizationStart(BaseModel):
    authorization_url: str

    model_config = ConfigDict(extra="forbid")


class GoogleAuthorizationCallback(BaseModel):
    # What Google put in the callback address. The code works once, for
    # a few minutes, and only with this server's client secret.
    code: str = Field(min_length=1, max_length=2048)
    state: str = Field(min_length=1, max_length=2048)

    model_config = ConfigDict(extra="forbid")

    def __repr__(self) -> str:
        return "GoogleAuthorizationCallback(<hidden>)"

    __str__ = __repr__
