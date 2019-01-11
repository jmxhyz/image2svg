#!/usr/bin/python

#------------------------------------------------------------------------
# Name: image2svg.py
# 
# Description:
# Convert an image file to a 6-shades svg "line art" file to 
# be printed on an XY Plotter
#
# An aliased & upscaled bitmap (~1600x1000) is preferable
# for optimal results.
#
# To be drawn on a XY plotter with no optimization, vectors 
# coords start from left to right, then right to left
# every other line.
#
# Version 3 - Use PIL Image instead of the now depreciated
#             scipy imread + major cleanup
#     Todo: investigate why PIL antialias/degrade jpg (open? convert?)
#           automate upscaling  ==> resize to 200 dpi
#-------------------------------------------------------------------------

from PIL import Image
import numpy as np
import codecs, sys


# Set visible to True to display the vector lines on screen (for testing)
# False to prevent G-Code generator from double-stroking each line (but produce invisible output on SVG viewers)

visible = True

# Shades thresholds. May require tweaking for better results on darker/lighter images
# Pixels values are reduced (darkened) to the nearest
# C64 palette vals: 0, 87, 96, 111, 114, 132, 158, 164, 173, 174, 212, 213, 230, 238, 255

shade1 = 0      # Black
shade2 = 50            
shade3 = 100         
shade4 = 158             
shade5 = 212
shade6 = 240

PIXEL_SIZE = 1 / (200.0 / 25.4)     # ? mm/px Calculate pixel size in MM based on IMAGE_DPI

POWER_MIN = 0
POWER_MAX = 15
FEED_SPEED = 300
FEED_SPEED_MAX = 800

POWER_STEP = float(POWER_MAX - POWER_MIN) / 6.0
SPEED_STEP = float(FEED_SPEED_MAX - FEED_SPEED) / 6.0

GCODE_HEADER = """;-- Laser gcode Head
M5
G90
G21
G0F8000
G1F%d
M3S1
G4P2
M5
G4P3
M3S0\n
"""

GCODE_FOOTER = """
;-- Laser gcode Footer
M5S0
G0X0Y0F8000
"""

S_OR_F = 0
MOVE_GCODE = "G0 X%.3f Y%.3f\n"       # %X, %Y 
BURN_GCODE = "S%.3f\nG1 X%.3f Y%.3f\n"  # %X, %Y, %S (laser power)
BURN_GCODE_F = "G1 X%.3f Y%.3f F%d\n"  # %X, %Y, %F (laser speed)

last_a = 0
last_b = 0
last_c = 0
last_d = 0


def MOVE_TO (x, y):
    if(x<0.001):
        x=0
    if(y<0.001):
        y=0
    return MOVE_GCODE % (x, y)

def BURN_TO (x, y, val):
    if(x<0.001):
        x=0
    if(y<0.001):
        y=0
    if S_OR_F==1:
        return BURN_GCODE_F % (x, y, val)
    else:
        return BURN_GCODE % (val, x, y)

#------ Functions definition ------#

def needLineX(val, rowIndex):   # Determine if a segment must be drawn depending on its shade & row number
    if rowIndex % 2 == 0 and val <= shade1:
        return True
    elif rowIndex % 4 == 0 and val <= shade3:
        return True
    elif rowIndex % 8 == 0 and val <= shade5:
        return True
    else:
        return False
    
def needLineY(val, rowIndex):
    if rowIndex % 2 == 0 and val <= shade1:
        return False    # Only draw horizontal lines
    elif rowIndex % 4 == 0 and val <= shade2:
        return True
    elif rowIndex % 4 == 0 and val <= shade3:
        return False    # Only draw horizontal lines
    elif rowIndex % 8 == 0 and val <= shade4:
        return True
    else:
        return False

def svgPrint(start, stop, rowNum, invert, axes, axisDimension, val): 
    if val != 0:
        val = (val // (256 // 6)) * ( 256 // 6 )
    l_color = ' style="stroke:rgb(%d,%d,%d);stroke-width:1"' % (val, val, val)
    svgFile.write('<line '+ axes[0] + '1="'
                  + str(axisDimension-start if invert == True else start)
                  + '" ' + axes[1] + '1="' + str(rowNum)
                  + '" ' + axes[0] + '2="'
                  + str(axisDimension-stop if invert == True else stop)
                  + '" ' + axes[1] + '2="' + str(rowNum) + '"' + l_color + ' />\n')
    
    global last_a, last_b , last_c ,last_d
    if S_OR_F==1:
        sval = val // (256 // 6) * SPEED_STEP + FEED_SPEED
    else:
        sval = (255-val) // (256 // 6) * POWER_STEP
    a = float(axisDimension-start if invert == True else start) * PIXEL_SIZE
    c = float(axisDimension-stop if invert == True else stop )  * PIXEL_SIZE
    b = d = float(rowNum) * PIXEL_SIZE
    if axes[0]=='x':
        if a!=last_c or b!=last_d:
            gcodeFile.write( MOVE_TO( a, b ) )
        gcodeFile.write( BURN_TO( c, d, sval ) )

    if axes[0]=='y':
        if a!=last_c or b!=last_d:
            gcodeFile.write( MOVE_TO( b, a ) )
        gcodeFile.write( BURN_TO( d, c, sval ) )
    last_a = a
    last_b = b
    last_c = c
    last_d = d


def generateVectors(img, needLine, axes, axisDimension):
    invert = False
    
    for rowIndex, row in enumerate(img):            # Go through each row
        rowDrawn = False
        firstEndpoint = 0
        
        if invert == True:      # Invert every other line where something is drawn on a row
            row = np.flipud(row)
        
        for index, pixel in enumerate(row):             # Go through each column  
            if index > 0 and pixel != row[index-1]:     # If the pixel color is different from the last
                if needLine(row[index-1], rowIndex):    # Check if this last segment must be "printed"
                    svgPrint(firstEndpoint, index, rowIndex, invert, axes, axisDimension, row[index-1])
                    rowDrawn = True
                firstEndpoint = index       # Store the first endpoint of the next line segment        
        
        if needLine(row[index], rowIndex):  # Test/Print last segment at the end of each line
            svgPrint(firstEndpoint, index, rowIndex, invert, axes, axisDimension, row[index])
            rowDrawn = True

        if rowDrawn == True:  
            invert = not invert

def main(inputFile, s_or_f):
    global S_OR_F
    if s_or_f == 1:
        S_OR_F = 1
    image = Image.open(inputFile).convert('L', dither=False) 
    image = image.transpose(Image.FLIP_TOP_BOTTOM)
    
    try:
        i_dpi = image.info['dpi']
    except:
        i_dpi = (72, 72)
    
    scale_w = 200.0 / i_dpi[0]
    scale_h = 200.0 / i_dpi[1]

    width, height = image.size           #pixel
    width = int(float(width) * scale_w + 0.5)
    height = int(float(height) * scale_h + 0.5)

    image = image.resize((width, height),Image.ANTIALIAS)
    # Reduce color to 6 shades
    image = Image.eval(image, lambda px: shade1 if px < shade2 else
                                        (shade2 if px < shade3 else
                                        (shade3 if px < shade4 else
                                        (shade4 if px < shade5 else
                                        (shade5 if px < shade6 else 255)))))

    # Convert image to array
    image = np.asarray(image)

    # Create SVG file + header
    global svgFile
    svgFile = codecs.open(inputFile + ".svg", "w+")
    svgFile.write('<?xml version="1.0" encoding="UTF-8" ?>\n')
    svgFile.write('<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n')
    svgFile.write('<svg width="'+ str(width)+ 'px" height="'+str(height)+'px" viewBox="0 0 '
                  + str(width)+ " " +str(height)+'" version="1.1" xmlns="http://www.w3.org/2000/svg">\n')

    # Stroke lines if option is set
    if visible == True:
        svgFile.write('<g stroke="black" stroke-width="1">\n')


    global gcodeFile
    gcodeFile = codecs.open(inputFile + ".gcode", "w+")
    gcodeFile.write( GCODE_HEADER % FEED_SPEED )
    if S_OR_F==1:
        gcodeFile.write( "S%d\n" % POWER_MAX )

    # Create X axis segments
    generateVectors(image, needLineX, ['x', 'y'], width)

    # Create Y axis segments
    image = np.swapaxes(image, 0, 1)
    generateVectors(image, needLineY, ['y', 'x'], height)

    # Close SVG file
    if visible == True:
        svgFile.write('</g>')
    svgFile.write('</svg>')
    svgFile.close()
    
    gcodeFile.write( GCODE_FOOTER )
    gcodeFile.close()
# End Main

if __name__ == "__main__":
    S_OR_F = 0
    try:
        if sys.argv[2]=="1":
            S_OR_F = 1
    except:
        S_OR_F = 0

    try:
        main(sys.argv[1], S_OR_F)
    except IndexError:
        print("No input file specified.")
        wait = input("Press enter to continue...")
        sys.exit(1)
    except FileNotFoundError:
        print("Input file not found.")
        wait = input("Press enter to continue...")
        sys.exit(1)
    except OSError:
        print("Image file not recognized.")
        wait = input("Press enter to continue...")
        sys.exit(1)
