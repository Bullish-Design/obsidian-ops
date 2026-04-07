from obsidian_ops import BusyError, PathError, SearchResult, Vault, VCSError


def test_public_api_imports() -> None:
    assert Vault is not None
    assert SearchResult is not None
    assert PathError is not None
    assert BusyError is not None
    assert VCSError is not None
