import os
import glob

files = glob.glob('src/agt/*.asl')
includes = '{ include("$jacamoJar/templates/common-cartago.asl") }\n{ include("$jacamoJar/templates/common-moise.asl") }\n\n'

for file in files:
    with open(file, 'r') as f:
        content = f.read()
    if 'common-cartago.asl' not in content:
        with open(file, 'w') as f:
            f.write(includes + content)

print("Includes added!")
