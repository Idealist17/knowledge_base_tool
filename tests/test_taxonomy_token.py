from learn_kg.taxonomy import resolve_taxonomy_entry, VulnerabilityCategory, taxonomy_prompt
from learn_kg.token_utils import chunk_text


def test_taxonomy_resolve_normalized():
    e = resolve_taxonomy_entry(VulnerabilityCategory.DenialOfServices, "DoS With Block Gas Limit")
    assert e and e.subcategory == "DoS with Block Gas Limit"
    assert "Access Control" in taxonomy_prompt()


def test_chunk_text():
    chunks = chunk_text("a " * 1000, 50)
    assert len(chunks) > 1
