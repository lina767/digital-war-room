"""
Tests for EntityRegistry: add, deduplicate, get_by_type, alias matching.
"""

from agents.entity_registry import _ALIAS_INDEX, EntityRegistry, NEREntity


class TestBasicOperations:
    def test_add_and_get_all(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="news"))
        assert reg.count == 1
        assert reg.get_all()[0].entity == "Iran"

    def test_add_many(self):
        reg = EntityRegistry()
        reg.add_many(
            [
                NEREntity(entity="Iran", type="LOCATION", source_agent="news"),
                NEREntity(entity="IRGC", type="ORG", source_agent="socmint"),
            ]
        )
        assert reg.count == 2

    def test_get_by_type(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="news"))
        reg.add(NEREntity(entity="IRGC", type="ORG", source_agent="news"))
        reg.add(NEREntity(entity="Tehran", type="LOCATION", source_agent="socmint"))
        assert len(reg.get_by_type("LOCATION")) == 2
        assert len(reg.get_by_type("ORG")) == 1
        assert len(reg.get_by_type("PERSON")) == 0


class TestDeduplication:
    def test_exact_duplicate_merged(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="news"))
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="socmint"))
        reg.deduplicate()
        assert reg.count == 1

    def test_case_insensitive_merge(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="iran", type="LOCATION", source_agent="news"))
        reg.add(NEREntity(entity="IRAN", type="LOCATION", source_agent="socmint"))
        reg.deduplicate()
        assert reg.count == 1

    def test_different_types_not_merged(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="news"))
        reg.add(NEREntity(entity="Iran", type="ORG", source_agent="socmint"))
        reg.deduplicate()
        assert reg.count == 2

    def test_alias_merge_irgc(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="IRGC", type="ORG", source_agent="news"))
        reg.add(NEREntity(entity="Islamic Revolutionary Guard Corps", type="ORG", source_agent="socmint"))
        reg.add(NEREntity(entity="Sepah", type="ORG", source_agent="sigint"))
        reg.deduplicate()
        assert reg.count == 1
        assert reg.get_all()[0].entity == "IRGC"

    def test_alias_merge_hezbollah(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Hezbollah", type="ORG", source_agent="news"))
        reg.add(NEREntity(entity="Hizballah", type="ORG", source_agent="socmint"))
        reg.deduplicate()
        assert reg.count == 1

    def test_alias_merge_isis(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="ISIS", type="ORG", source_agent="news"))
        reg.add(NEREntity(entity="Daesh", type="ORG", source_agent="socmint"))
        reg.add(NEREntity(entity="Islamic State", type="ORG", source_agent="techint"))
        reg.deduplicate()
        assert reg.count == 1

    def test_higher_confidence_preserved(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="IRGC", type="ORG", source_agent="news", confidence=0.5))
        reg.add(NEREntity(entity="Sepah", type="ORG", source_agent="socmint", confidence=0.9))
        reg.deduplicate()
        assert reg.get_all()[0].confidence == 0.9


class TestAliasIndex:
    def test_known_aliases_in_index(self):
        assert "irgc" in _ALIAS_INDEX
        assert "sepah" in _ALIAS_INDEX
        assert _ALIAS_INDEX["sepah"] == "IRGC"

    def test_hezbollah_aliases(self):
        assert _ALIAS_INDEX.get("hizballah") == "Hezbollah"
        assert _ALIAS_INDEX.get("hizbullah") == "Hezbollah"


class TestToList:
    def test_serializes_to_dicts(self):
        reg = EntityRegistry()
        reg.add(NEREntity(entity="Iran", type="LOCATION", source_agent="news"))
        result = reg.to_list()
        assert isinstance(result, list)
        assert result[0]["entity"] == "Iran"
        assert result[0]["type"] == "LOCATION"
