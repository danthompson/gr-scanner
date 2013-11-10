/* -*- c++ -*- */

#define SCANNER_API

%include "gnuradio.i"			// the common stuff

//load generated python docstrings
%include "scanner_swig_doc.i"

%{
#include "scanner/crc.h"
#include "scanner/deinterleave.h"
%}


%include "scanner/crc.h"
GR_SWIG_BLOCK_MAGIC2(scanner, crc);

%include "scanner/deinterleave.h"
GR_SWIG_BLOCK_MAGIC2(scanner, deinterleave);
