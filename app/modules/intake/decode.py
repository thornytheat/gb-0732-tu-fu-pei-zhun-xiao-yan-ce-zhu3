import codecs

from app.errors import RegisterError


def decode_table(raw, filename):
    encodings = ('utf-8-sig',) if raw.startswith(codecs.BOM_UTF8) else ('utf-8', 'gb18030')
    for encoding in encodings:
        try:
            text = raw.decode(encoding)
            if '\x00' in text:
                raise RegisterError('BAD_ENCODING', '表格包含空字节', evidence=filename)
            return text, encoding
        except UnicodeDecodeError as error:
            offset = error.start
    raise RegisterError('BAD_ENCODING', '无法识别点表编码', evidence={'file': filename, 'byte': offset})
