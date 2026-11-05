import ast

chunk = '''def malformed_json_strategy() -> st.SearchStrategy[str]:
    """Generate malformed JSON strings."""
    return st.sampled_from([
        "{NOT VALID JSON}",
        '{"key": "value"}',
        '{"key": }',
        "{'key': 'value'}",
        '{"key": undefined}',
        "",
        "{",
        "}",
    ])'''

try:
    ast.parse(chunk)
    print('OK')
except SyntaxError as e:
    print(f'Error: {e}')
    print(f'Line {e.lineno}: {e.text}')