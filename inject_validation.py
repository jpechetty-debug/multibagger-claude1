import re

with open('Newmultibagger-main/app_routes/stocks.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add validation logic
validation_code = '''
import re

_SYMBOL_RE = re.compile(r"^[A-Z0-9&]{1,20}(\.(NS|BO|BSE))?$", re.IGNORECASE)

def _validate_symbol(symbol: str) -> str:
    s = symbol.strip().upper()
    if not _SYMBOL_RE.match(s):
        raise HTTPException(status_code=422, detail=f"Invalid symbol: {symbol!r}")
    return s

'''

# Insert validation code before router = APIRouter()
content = content.replace('router = APIRouter()', validation_code + 'router = APIRouter()')

def repl(m):
    return m.group(1) + m.group(2) + 'try:\n' + m.group(2) + '    symbol = _validate_symbol(symbol)'

# regex to find function signatures with symbol: str, followed by optional docstring and try:
pattern = r'(async def [^\(]*\([^\)]*symbol:\s*str[^\)]*\):(?:(?:\s*\"\"\"[^\"]*\"\"\")|(?:\s*\'\'\'[^\']*\'\'\'))?\s+)(\s*)(try:)'

content = re.sub(pattern, repl, content)

with open('Newmultibagger-main/app_routes/stocks.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Replacement done.")
