def load_config():
    config = {}
    with open('SETUP.txt', 'r') as file:
        for line in file:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('#')
                key_value_part = parts[0].strip()
                key, value = key_value_part.split(': ')
                # Convertir el valor de debug en booleano
                if key == 'debug':
                    config[key] = value.lower() == 'true'
                else:
                    config[key] = value
    return config