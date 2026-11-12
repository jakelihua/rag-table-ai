from rag_table_ai import RagTableAI


def test_rag_table_ai_facade():
    engine = RagTableAI()

    # 1. Flatten
    md = "| Item | Cost |\n| --- | --- |\n| Widget | $50 |"
    flat = engine.flatten(md)
    assert "- [Row 1] Item: Widget | Cost: $50" in flat

    # 2. Match
    assert engine.match("10-20kg", "15kg")
    assert not engine.match("10-20kg", "25kg")

    # 3. Calculate
    assert engine.calculate("200 * 80%") == "160.00"

    # 4. Split
    chunks = engine.split_table(md)
    assert len(chunks) == 1
    assert "Item" in chunks[0].headers
