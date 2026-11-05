import ast

code = b'''
def malformed_json_strategy() -> st.SearchStrategy[str]:
    return st.sampled_from([
        "{NOT VALID JSON}",
        '{"key": "value"}',
        '{"key": }',
        "{'key': 'value'}",
        '{"key": undefined}',
        "",
        "{",
        "}",
    ])
'''

ast.parse(code.decode('utf-8'))
print('OK')