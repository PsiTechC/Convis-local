from pydantic import BaseModel, EmailStr

class Login(BaseModel):
    email: EmailStr
    password: str

class LoginResponse(BaseModel):
    redirectUrl: str
    clientId: str
    isAdmin_683ed29d13d9992915a2a803_amdin_: bool
    token: str
