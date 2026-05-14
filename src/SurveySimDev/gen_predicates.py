
predicates = [
    "c_visw_H2O_no",
    "c_visw_H2O_yes_CH4_yes",
    "c_visw_H2O_yes",
    "c_viso_O2_high",
    "c_viso_O2_medium",
    "c_viso_O2_no",
    "c_nir_CH4_no",
    "c_nir_CH4_yes",
    "c_nir_CH4_yes_CO2_yes",
    "c_nir_ok",
    "c_nir_CO2_no",
    "c_nir_CO2_yes",
    "c_nuv_press_low",
    "c_nuv_press_high",
    "c_nuv_press_low",
    "c_nuv_press_high",
    "c_nuv_O3_no",
    "c_nuv_O3_yes"
    ]

any_template = '''
    def {f_name}(self, mode=None, retrieval=None):
        # ensure there was a char
        if self.n_char_ok[mode] == 0:
            return False
        return True
'''

## -- Don't want this here b/c final char will exceed
##        # ensure chars not exceeded
##        if self.n_char[mode] >= self.n_char_remove:
##            return False

template = '''
    def {f_name}(self, mode=None, retrieval=None):
        # ensure there was a char
        if (not retrieval) or (not retrieval['char_ok']):
            return False
        analysis = retrieval['analysis']
        rv = True
        qois = [{qois}]
        vals = [{vals}]
        for qoi, val in zip(qois, vals):
            if analysis[qoi] != val:
                rv = False
        return rv
'''

print('# Generated file')
print('')
print('class StarInfoTreeMixin:')

for p in predicates:
    parts = p.split("_")
    f_name = p
    meas = parts[1] # e.g., "nuv"
    tail = parts[2:]
    #print(f"% {f_name}")
    if parts[2] == 'ok':
        print(any_template.format(f_name=f_name))
    else:
        qois = ', '.join([f'"{s}"' for s in tail[0::2]])
        vals = ', '.join([f'"{s}"' for s in tail[1::2]])
        print(template.format(f_name=f_name,
                              meas=meas,
                              qois=qois,
                              vals=vals))

    
