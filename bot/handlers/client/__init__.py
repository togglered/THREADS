from aiogram import Router


client_router = Router()

LIST_SEPARATOR = '|'
ERROR_SIGN = '⚠️'
SUCCESS_SIGN = '✅'
LOADING_SIGN = '🔄'

from .accounts import *
from .main import *
from .persona import *
from .schedule import *
from .media import *
from .auth import *
from .options import *