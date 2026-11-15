"""Version à prononcer, distincte du texte éditorial et des preuves conservées."""
import re
VERSION='spoken-fr-v1'


def prepare(text,strip_references=False):
    # Les nombres scientifiques restent présents ; seules les références de publication sont retirées.
    if strip_references:text=re.sub(r'\[\s*\d+(?:\s*[,;–-]\s*\d+)*\s*\]','',text)
    text=re.sub(r'\((?:voir\s+)?(?:fig(?:ure)?\.?|tableau)\s*\d+(?:\.\d+)*(?:\s*[,;]\s*\d+(?:\.\d+)*)*\)', '',text, flags=re.I)
    units={'mW':'milliwatts','MW':'mégawatts','W':'watts','dBm':'décibels milliwatts','dB':'décibels','GHz':'gigahertz','MHz':'mégahertz','THz':'térahertz','nm':'nanomètres','km':'kilomètres','ms':'millisecondes','%':'pour cent'}
    pattern=r'(?<!\w)(\d+(?:[.,]\d+)?)\s*('+('|'.join(re.escape(v) for v in sorted(units,key=len,reverse=True)))+r')(?!\w)'
    text=re.sub(pattern,lambda m:m[1].replace('.',',')+' '+units[m[2]],text)
    greek={'β':'bêta','α':'alpha','λ':'lambda','Δ':'delta','φ':'phi','γ':'gamma'}
    for symbol,name in greek.items():text=re.sub(re.escape(symbol)+r'\s*([0-9]+)?',lambda m:name+(' '+m[1] if m[1] else '')+' ',text)
    return re.sub(r'\s+',' ',text).strip()
