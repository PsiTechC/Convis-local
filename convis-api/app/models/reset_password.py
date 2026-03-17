from pydantic import BaseModel, EmailStr, Field

class ResetPassword(BaseModel):
    email: EmailStr
    newPassword: str = Field(..., min_length=6)

class ResetPasswordResponse(BaseModel):
    message: str
