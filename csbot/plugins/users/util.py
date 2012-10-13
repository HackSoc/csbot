def needs_db(fn):
    def decorator():
        if hasattr(User, 'db'):
            fn()
        else:
            raise DatabaseNotSet("You need to set up the database before calling {}".format(fn.__name__))
    return decorator

