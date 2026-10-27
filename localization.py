import re


class Translator:
    """Exact labels and anchored templates; channel names/URLs remain unchanged."""
    def __init__(self, translations):
        self.translations = translations
        self.patterns = []
        for source, target in translations.items():
            if '{0}' in source:
                parts = re.split(r'(\{\d+\})', source)
                pattern = ''.join('(.*?)' if re.fullmatch(r'\{\d+\}', p) else re.escape(p) for p in parts)
                self.patterns.append((re.compile('^' + pattern + '$', re.DOTALL), target))

    def __call__(self, text):
        if text in self.translations:
            return self.translations[text]
        for pattern, target in self.patterns:
            match = pattern.fullmatch(text)
            if match:
                return target.format(*match.groups())
        return text
