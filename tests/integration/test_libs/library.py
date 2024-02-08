class ComplicatedObject:
    """A simple class."""
    var = 0

    def set(self, v: int) -> None:
        """Set variable of instance."""
        self.var = v

    def get(self) -> int:
        """Get variable from instance."""
        return self.var


def create_complicated_object() -> ComplicatedObject:
    """Wrapper function to create and return an object."""
    return ComplicatedObject()


def set_co(co: ComplicatedObject, v: int) -> None:
    """Wrapper function to set variable on object."""
    co.set(v)


def get_co(co: ComplicatedObject) -> int:
    """Wrapper function to get variable from object."""
    return co.get()


def do_something(action: str) -> None:
    """Simulate to do something on the server (like print)."""
    print("Do ", action)  # noqa: T201


def get_double(number: int) -> int:
    """Simulate a transformation on the server (calculate the double)."""
    return number * 2
