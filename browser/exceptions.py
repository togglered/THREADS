class CustomExceptions:
    class LoginCredentialsInvalid(Exception):
        pass
    class NoCookiesProvided(Exception):
        pass
    class CookieInvalid(Exception):
        pass