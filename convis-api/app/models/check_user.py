from pydantic import BaseModel, EmailStr

class CheckUser(BaseModel):
    email: EmailStr

class CheckUserResponse(BaseModel):
    exists: bool
