from nanoid import generate

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
DEFAULT_SIZE = 7


def generate_shortcode(size: int = DEFAULT_SIZE) -> str:
    return generate(ALPHABET, size)


def estimate_collision_probability(n_ids: int, size: int = DEFAULT_SIZE) -> float:
    """
    Birthday problem approximation.
    At alphabet=62 chars, size=7: ~3.5 trillion combinations.
    Collision probability reaches ~1% only after ~26 million IDs.
    """
    space = len(ALPHABET) ** size
    return 1 - (1 - (n_ids / space)) ** n_ids