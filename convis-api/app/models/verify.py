from pydantic import BaseModel, EmailStr

class VerifyEmail(BaseModel):
    email: EmailStr
    otp: str

class VerifyResponse(BaseModel):
    message: str
