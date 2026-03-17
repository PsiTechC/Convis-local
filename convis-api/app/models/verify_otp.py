from pydantic import BaseModel, EmailStr

class VerifyOTP(BaseModel):
    email: EmailStr
    otp: str

class VerifyOTPResponse(BaseModel):
    message: str
