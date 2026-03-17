from pydantic import BaseModel, EmailStr

class SendOTP(BaseModel):
    email: EmailStr

class SendOTPResponse(BaseModel):
    message: str
