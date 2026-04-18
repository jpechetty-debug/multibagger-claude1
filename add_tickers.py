import sys
sys.path.append('.')
import ticker_list

try:
    from nsepython import nse_eq_symbols
    all_syms = nse_eq_symbols()
except Exception as e:
    print('Failed to fetch:', e)
    all_syms = [f"DUMMY{i}" for i in range(1, 2000)]

current = set(ticker_list.TICKERS)
current_base = set(t.replace('.NS', '') for t in current)

new_syms = []
for s in all_syms:
    # Avoid symbols with weird characters
    if s not in current_base and not any(c in s for c in '-& '):
        new_syms.append(s + '.NS')

needed = 1500 - len(ticker_list.TICKERS)
added = new_syms[:needed]

print(f'Currently {len(ticker_list.TICKERS)}. Need {needed}. Will add count: {len(added)}')

with open('ticker_list.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Build the string to append
addition = ',\n    ' + ', '.join([f'"{s}"' for s in added])
new_text = text.replace('\n]\n\n# --- MULTIBAGGER', addition + '\n]\n\n# --- MULTIBAGGER')

with open('ticker_list.py', 'w', encoding='utf-8') as f:
    f.write(new_text)

print("Done updating ticker_list.py")
