from django import template

register = template.Library()


@register.filter
def nbsp_dash(text):
    """Тире не уезжает в начало строки: пробел перед ним становится неразрывным
    (как &nbsp;— в «Обо мне»). Работает и для текстов, набранных в админке."""
    return str(text).replace(' —', ' —')


@register.filter
def gear_lines(text):
    """«Камера + объективы; другая камера + …» → по строке на каждую камеру.
    Внутри названия камеры или объектива пробелы неразрывные: перенос — только
    между камерой и объективом или между объективами, а не посреди «F1.4 GM»."""
    lines = []
    for part in str(text).split(';'):
        if part.strip():
            items = [i.strip().replace(' ', '\u00a0') for i in part.replace(', ', ' + ').split(' + ')]
            lines.append(' + '.join(items))
    return lines
