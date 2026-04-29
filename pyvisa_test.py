import pyvisa

visaAddress = "TCPIP0::10.76.79.222::inst0::INSTR"
pyVNA = pyvisa.ResourceManager().open_resource(visaAddress)
print(pyVNA.query("*idn?").rstrip())

# Query measurement numbers within a given channel
# SCPI: system:measure:catalog? <CH#>
print(pyVNA.query("system:measure:catalog?").rstrip())
print(pyVNA.query("system:measure:catalog? 1").rstrip())
print(pyVNA.query("system:measure:catalog? 2").rstrip())
print(pyVNA.query("system:measure:catalog? 3").rstrip())

pyVNA.write("calculate1:measure1:data:snp:ports:save '1 ,2', 'D:\PSIG_remote_share_folder\Malagueta_substrate\dut_test_calToProbe.s2p'")
pyVNA.write("calculate2:measure2:data:snp:ports:save '1 ,3, 2, 4', 'D:\PSIG_remote_share_folder\Malagueta_substrate\dut_test_calToProbe.s4p'")