# -*- coding: utf-8 -*-
# @Author: Dongqing Sun
# @E-mail: Dongqingsun96@gmail.com
# @Date:   2021-03-16 13:37:31
# @Last Modified by:   Dongqing Sun
# @Last Modified time: 2021-03-16 21:55:58


import os, sys
import time
import tables
import h5py
import re
import collections
import numpy as np
import scipy.sparse as sp_sparse
import argparse as ap
import pandas as pd

from pkg_resources import resource_filename

from MAESTRO.scATAC_utility import *
from MAESTRO.scATAC_H5Process import *

def barcodemap_parser(subparsers):
    """
    Add main function init-scatac argument parsers.
    """

    workflow = subparsers.add_parser("multiome-barcode-map", 
        help = "Transfer barcodes between RNA and ATAC. Only barcodes contained by both libraries will be remained. ")
    group_input = workflow.add_argument_group("Input arguments")
    group_input.add_argument("--format", dest = "format", default = "", 
        choices = ["h5", "mtx", "plain"], 
        help = "Format of the count matrix file. Please make the format of peak and RNA counts consistent. ")
    group_input.add_argument("--peakcount", dest = "peakcount", default = "", 
        help = "Location of peak count matrix file. "
        "Peak count matrix with peaks as rows and cells as columns. "
        "If the format is 'h5' or 'plain', users need to specify the name of the count matrix file "
        "and row names should be like 'chromosome_peakstart_peakend', such as 'chr10_100020591_100020841'. "
        "If the format is 'mtx', the 'matrix' should be the name of .mtx formatted matrix file, such as 'matrix.mtx'.")
    group_input.add_argument("--genecount", dest = "genecount", default = "", 
        help = "Location of gene count matrix file. "
        "If the format is 'h5' or 'plain', users need to specify the name of the count matrix file. "
        "If the format is 'mtx', the 'matrix' should be the name of .mtx formatted matrix file, such as 'matrix.mtx'.")
    group_input.add_argument("--separator", dest = "separator", default = "tab", 
        choices = ["tab", "space", "comma"],
        help = "The separating character (only for the format of 'plain'). "
        "Values on each line of the plain matrix file will be separated by the character. DEFAULT: tab.")
    group_input.add_argument("--atac-feature", dest = "atac_feature", default = "", 
        help = "Location of feature file (required for the format of 'mtx'). "
        "Features correspond to row indices of count matrix. "
        "The feature file should be the peak bed file with 3 columns. For example, peaks.bed.")
    group_input.add_argument("--atac-barcode", dest = "atac_barcode", default = "", 
        help = "Location of barcode file (required for the format of 'mtx'). "
        "Cell barcodes correspond to column indices of count matrix. For example, barcodes.tsv. ")
    group_input.add_argument("--rna-feature", dest = "rna_feature", default = "features.tsv", 
        help = "Location of feature file (required for the format of 'mtx'). "
        "Features correspond to row indices of count matrix. DEFAULT: features.tsv.")
    group_input.add_argument("--gene-column", dest = "gene_column", default = 2, type = int,
        help = "If the format is 'mtx', please specify which column of the feature file to use for gene names. DEFAULT: 2.")
    group_input.add_argument("--rna-barcode", dest = "rna_barcode", default = "barcodes.tsv", 
        help = "Location of barcode file (required for the format of 'mtx'). "
        "Cell barcodes correspond to column indices of count matrix. DEFAULT: barcodes.tsv. ")
    group_input.add_argument("--atac-barcode-lib", dest = "atac_barcode_lib", default = "", 
        help = "Location of ATAC barcode library file. "
        "If the multiome data is generated by 10X genomics platform, the barcode library file is located at "
        "<path_to_cellrangerarc>/cellranger-arc-1.0.1/lib/python/atac/barcodes. "
        "The two sets of barcodes from RNA and ATAC should be associated by line number. "
        "For example, the barcode from line 1748 of the RNA barcode list is associated with the barcode from line 1748 of the ATAC barcode list. ")
    group_input.add_argument("--rna-barcode-lib", dest = "rna_barcode_lib", default = "", 
        help = "Location of RNA barcode library file. "
        "If the multiome data is generated by 10X genomics platform, the barcode library file is located at "
        "<path_to_cellrangerarc>/cellranger-arc-1.0.0/lib/python/cellranger/barcodes. "
        "The two sets of barcodes from RNA and ATAC should be associated by line number. "
        "For example, the barcode from line 1748 of the RNA barcode list is associated with the barcode from line 1748 of the ATAC barcode list. ")
    group_input.add_argument("--species", dest = "species", default = "GRCh38", 
        choices = ["GRCh38", "GRCm38"], type = str, 
        help = "Species (GRCh38 for human and GRCm38 for mouse). DEFAULT: GRCh38.")
 
    group_output = workflow.add_argument_group("Output arguments")
    group_output.add_argument("--rna-to-atac", dest = "rna_to_atac", action = "store_true",
        help = "Whether or not to translate RNA barcodes to the corresponding entry on the ATAC barcode list. If set, "
        "MAESTRO will translate RNA barcodes to the corresponding entry on the ATAC barcode list. "
        "If not (by default), MAESTRO will translate ATAC barcodes to the corresponding entry on the RNA barcode list. ")
    group_output.add_argument("-d", "--directory", dest = "directory", default = "MAESTRO", 
        help = "Path to the directory where the result file shall be stored. DEFAULT: MAESTRO.")
    group_output.add_argument("--outprefix", dest = "outprefix", default = "MAESTRO", 
        help = "Prefix of output files. DEFAULT: MAESTRO.")


def barcodemap(fileformat, directory, outprefix, rna_to_atac, peakcount, genecount, atac_feature, atac_barcode, 
    rna_feature, gene_column, rna_barcode, atac_barcode_lib, rna_barcode_lib, species):
    try:
        os.makedirs(directory)
    except OSError:
        # either directory exists (then we can ignore) or it will fail in the
        # next step.
        pass
    
    if fileformat == "plain":
        matrix_dict = read_count(peakcount, separator)
        peakmatrix = matrix_dict["matrix"]
        peakmatrix = sp_sparse.csc_matrix(peakmatrix, dtype=np.int32)
        atac_features = matrix_dict["features"]
        atac_features = [f.encode() for f in atac_features]
        atac_barcodes = matrix_dict["barcodes"]

        matrix_dict = read_count(genecount, separator)
        genematrix = matrix_dict["matrix"]
        genematrix = sp_sparse.csc_matrix(genematrix, dtype=numpy.float32)
        rna_features = matrix_dict["features"]
        rna_barcodes = matrix_dict["barcodes"]

    elif fileformat == "h5":
        scatac_count = read_10X_h5(peakcount)
        peakmatrix = scatac_count.matrix
        atac_features = scatac_count.names.tolist()
        atac_features = [re.sub("\W", "_", feature.decode()) for feature in atac_features]
        atac_features = [feature.encode() for feature in atac_features]
        atac_barcodes = scatac_count.barcodes.tolist()

        scrna_count = read_10X_h5(genecount)
        genematrix = scrna_count.matrix
        rna_features = scrna_count.names.tolist()
        rna_barcodes = scrna_count.barcodes.tolist()

        if type(rna_features[0]) == bytes:
            rna_features = [i.decode() for i in rna_features]
        if type(rna_barcodes[0]) == bytes:
            rna_barcodes = [i.decode() for i in rna_barcodes]

    elif fileformat == "mtx":
        matrix_dict = read_10X_mtx(matrix_file = peakcount, feature_file = atac_feature, barcode_file = atac_barcode, datatype = "Peak")
        peakmatrix = matrix_dict["matrix"]
        atac_features = matrix_dict["features"]
        atac_features = [f.encode() for f in atac_features]
        atac_barcodes = matrix_dict["barcodes"]

        matrix_dict = read_10X_mtx(matrix_file = genecount, feature_file = rna_feature, barcode_file = rna_barcode, datatype = "Gene", gene_column = gene_column)
        genematrix = matrix_dict["matrix"]
        rna_features = matrix_dict["features"]
        rna_barcodes = matrix_dict["barcodes"]

    # read barcode file
    atac_barcode_lib_list = []
    fhd = universal_open(atac_barcode_lib, "rt" )
    for line in fhd:
        line = line.strip()
        atac_barcode_lib_list.append(line)
    fhd.close()

    rna_barcode_lib_list = []
    fhd = universal_open(rna_barcode_lib, "rt" )
    for line in fhd:
        line = line.strip()
        rna_barcode_lib_list.append(line)
    fhd.close()

    atac_rna_dict = dict(zip(atac, rna))
    rna_atac_dict = dict(zip(rna, atac))
    
    if rna_to_atac:
        rna_atac_barcodes = [rna_atac_dict[i] for i in rna_barcodes]
        barcode_overlapped = list(set(rna_atac_barcodes) & set(atac_barcodes))
        rna_barcode_idx = [barcode_overlapped.index(i) for i in barcode_overlapped]
        atac_barcode_idx = [barcode_overlapped.index(i) for i in atac_barcodes]
    else:
        atac_rna_barcodes = [atac_rna_dict[i] for i in atac_barcodes]
        barcode_overlapped = list(set(atac_rna_barcodes) & set(rna_barcodes))
        atac_barcode_idx = [barcode_overlapped.index(i) for i in atac_rna_barcodes]
        rna_barcode_idx = [barcode_overlapped.index(i) for i in rna_barcodes]
    
    genematrix_filtered = genematrix[np.array(rna_barcode_idx), :]
    peakmatrix_filtered = peakmatrix[np.array(atac_barcode_idx), :]
    passed_genes = np.array(feature)[passed_gene.tolist()[0]].tolist()
    
    all_feature_matrix = np.vstack((genematrix_filtered, peakmatrix_filtered))
    all_features = rna_features + atac_features

    write_10X_h5(outprefix + "_multiome_gene_count.h5", matrix = genematrix_filtered, features = rna_features, barcodes = barcode_overlapped, genome = species, datatype = 'Gene')
    write_10X_h5(outprefix + "_multiome_peak_count.h5", matrix = peakmatrix_filtered, features = atac_features, barcodes = barcode_overlapped, genome = species, datatype = 'Peak')
    write_10X_h5_multiome(filename = outprefix + "_multiome_feature_count.h5", rna_matrix = genematrix_filtered, rna_features = rna_features, barcodes = barcode_overlapped, 
        atac_matrix = peakmatrix_filtered, atac_features = atac_features, genome = species, datatype = 'Multiome'):

