# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 11:51:01 2022

@author: Tano_E
"""

'''
1. Septic Load Calculation:
    Input: Watershed, Waterbody, avg number of people per household, and folder location
    Output: Provides lake spetic load results and shapefiles of septic system within 200m of waterbody.
'''
import os
import arcpy
import pandas as pd
import numpy as np
import xlsxwriter
from pathlib import Path
from collections import OrderedDict
import sys
from openpyxl import load_workbook

from math import pi
from bokeh.palettes import viridis
from bokeh.plotting import figure, show
from bokeh.transform import cumsum
from bokeh.io import save, output_file, export_png
from bokeh.layouts import column

arcpy.env.overwriteOutput = True

#  the folder path should prob be a class variable
class Septic:
    def __init__(self, watershed_input, waterbody_input, people, folder_location,
    septic_input = r"\\FLDEP1\giscloud\SepticTanks\DOH_FWMI\FWMI.gdb\Statewide_Septic_Centroids_2017_2018"):
        self.watershed = watershed_input
        self.waterbody = waterbody_input
        self.septic = septic_input
        self.people = people
        self.folder = folder_location

    def clipTanks(self):
        '''
        Clips septic tanks to watershed input and selects tanks by query of Known Septic, Likely Septic, or
        Somewhat likely septic. The selected tanks are then copied to another variable and a count is performed.
        '''
        temp_folder_path = os.path.join(self.folder, 'Septic_shapefiles')

        # Create folder if does not exist
        if not os.path.exists(temp_folder_path):
             os.mkdir(temp_folder_path)

        # Clip septic tanks to watershed
        watershed_clip = temp_folder_path + "\watershed_septic.shp"
        arcpy.Clip_analysis(self.septic, self.watershed, watershed_clip)

        ##Select only known, likely, and somewhat likely septic tanks
        query_septic = "WW = 'KnownSeptic' OR WW = 'LikelySeptic'  OR WW = 'SWLSeptic'"
        arcpy.MakeFeatureLayer_management(watershed_clip, "watershed_septic_lyr")
        wshed_septic = arcpy.SelectLayerByAttribute_management("watershed_septic_lyr", "NEW_SELECTION", query_septic)

        selectionTanks = arcpy.CopyFeatures_management(wshed_septic, temp_folder_path + "\known_likely_wshed_septic") # why does this not work here???

        septic_count = int(arcpy.GetCount_management(selectionTanks).getOutput(0))
        arcpy.AddMessage("There are approximately " + str(septic_count) +
                         " septic tanks in the watershed.")
        return selectionTanks, temp_folder_path

    def Buffer(self, selectionTanks, temp_folder_path):
        '''
        Takes output from clipTanks() and buffers septic within 200 meters of the waterbody input. Another count is done
        to show how many spetic tanks are within the buffered 200 meters.
        '''
        ##Create buffer zone around waterbody
        path_for_buffer = temp_folder_path + "\waterbody_buffer_zone.shp"
        arcpy.Buffer_analysis(self.waterbody, path_for_buffer, "200 meters")

        ##Clip watershed septic tanks to buffer zone
        path_for_clip = temp_folder_path + r"\buffer_septic.shp"
        arcpy.Clip_analysis(selectionTanks, path_for_buffer, path_for_clip)
        ##Get number of septic tanks within buffer
        septic_buffer_count = int(arcpy.GetCount_management(path_for_clip).getOutput(0))
        arcpy.AddMessage("There are approximately " + str(septic_buffer_count) +
                         " septic tanks within 200m of the waterbody.")
        return septic_buffer_count

    def runCalculation(self, septic_buffer_count):
        '''
        Takes output from Buffer() and performs septic calculations.

        *Note: This function creates the optional septic_loading for the pieChart() function in the PLSM class.
        '''

        septic_DF = pd.DataFrame(columns=["Parameter", "Value"])

        water_use = 70
        flow_loss = 0.85
        nitrogen = 9.012
        attenuation = 0.5

        septic_DF['Parameter'] = ["", "Septic Tanks", "Avg. People", "Water Use (gal/day)", "Flow Loss (15%)",
                                  "Nitrogen per person (lbs)", "Attenuation", "", "", "", "Flow Rate (gal/day/tank)",
                                  "Total Flow Rate (gal/yr)", "Total Flow Rate (L/yr)", "Total Flow Rate (hm3/yr)",
                                  "Nitrogen load (lbs)", "Nitrogen load (ug)", "", "", "Concentration (ug/L)"]

        septic_DF.loc[[1], 'Value'] = septic_buffer_count
        septic_DF.loc[[2], 'Value'] = self.people
        septic_DF.loc[[3], 'Value'] = water_use
        septic_DF.loc[[4], 'Value'] = flow_loss
        septic_DF.loc[[5], 'Value'] = nitrogen
        septic_DF.loc[[6], 'Value'] = attenuation
        septic_DF.loc[[10], 'Value'] = self.people*water_use*flow_loss
        septic_DF.loc[[11], 'Value'] = septic_buffer_count*float(septic_DF.loc[[10], 'Value'])*365
        septic_DF.loc[[12], 'Value'] = float(septic_DF.loc[[11], 'Value'])*3.78541
        septic_DF.loc[[13], 'Value'] = float(septic_DF.loc[[12], 'Value']*0.000000001)
        septic_DF.loc[[14], 'Value'] = self.people*nitrogen*septic_buffer_count*attenuation # this value
        septic_DF.loc[[15], 'Value'] = float(septic_DF.loc[[14], 'Value'])*453600000
        septic_DF.loc[[18], 'Value'] = int(float(septic_DF.loc[[15], 'Value']/float(septic_DF.loc[[12], 'Value'])))

        # convert lbs to kg
        septic_loading_Kg = [(self.people*nitrogen*septic_buffer_count*attenuation/2.205)]
        col_head = ['LEVEL1_L_1', "TN_Kg"]
        septic_list = ["Septic Load (Kg)"]

        septic_loading = pd.DataFrame(list(zip(septic_list, septic_loading_Kg)),
                          columns = col_head)
        ##Delete headers
        septic_DF = septic_DF.rename(columns={'Parameter': '', 'Value': ''})

        return septic_loading, septic_DF

    def to_excel(self, septic_DF):
        '''
        Takes input from runCalculation() sends septic loading to produce and format Septic_Calculations.xlsx
        '''
        #write dataframe to excel spreadsheet
        filepath = Path(self.folder + "\Septic_Calculations.xlsx")

        writer = pd.ExcelWriter(self.folder + "\Septic_Calculations.xlsx", engine='xlsxwriter')
        septic_DF.to_excel(writer, sheet_name='Results', index=False, header=False)

        if filepath.is_file():
            arcpy.AddWarning("WARNING: Septic Calculation spreadsheet (in chosen location) already exists. Previous file was " +
                     "overwritten! If you want to run this for an additional watershed, please select another folder " +
                     "location.")

        ##highlight cells for bathtub inputs
        workbook = writer.book
        worksheet = writer.sheets['Results']
        worksheet.set_column('A:A', 23, None)
        worksheet.set_column('B:B', 15, None)

        row_fmt = workbook.add_format()
        row_fmt.set_pattern(1)
        row_fmt.set_bg_color('yellow')

        worksheet.conditional_format(13, 1, 13, 1, {'type': 'cell', 'criteria': 'equal to', 'value': 'B$14', 'format': row_fmt})
        worksheet.conditional_format(18, 1, 18, 1, {'type': 'cell', 'criteria': 'equal to', 'value': 'B$19', 'format': row_fmt})

        writer.save()

