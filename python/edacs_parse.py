#!/usr/bin/env python

class data_field:
  def __init__(self, data):
    self.data = data
    self.fields = self.parse()

  types = { }
  offset = 0   #field offset applied to all fields. used for offsetting
               #subtypes to reconcile with the spec. Really just for readability.

  #get a particular field from the data
  def __getitem__(self, fieldname):
    mytype = self.get_type()
    if mytype in self.types:
      if fieldname in self.fields: #verify it exists in this packet type
        return self.fields[fieldname]
      else:
        raise FieldNotInPacket(fieldname)
    else:
      raise NoHandlerError(mytype)

  #grab all the fields in the packet as a dict
  #done once on init so you don't have to iterate down every time you grab a field
  def parse(self):
    fields = {}
    mytype = self.get_type()
    if mytype in self.types:
      for field in self.types[mytype]:
        bits = self.types[self.get_type()][field]
        if len(bits) == 3:
          obj = bits[2](self.get_bits(bits[0], bits[1]))
          fields.update(obj.parse())
          fields.update({field: obj})
        else:
          fields.update({field: self.get_bits(bits[0], bits[1])})
    else:
      raise NoHandlerError(mytype)
    return fields

  def get_type(self):
    raise NotImplementedError

  def get_numbits(self):
    raise NotImplementedError

  def get_bits(self, *args):
    startbit = args[0]
    num = args[1]
    bits = 0
    try:
      bits = (self.data \
        >> (self.get_numbits() - startbit - num + self.offset)) \
         & ((1 << num) - 1)
    except ValueError:
      pass
    return bits

class edacs_id_data(data_field):
  offset = 16
  types = {
      0x00: {"type": (16, 1), "agency": (17, 3), "fleet": (20, 4), "subfleet": (24, 4)},
      0x01: {"type": (16, 1), "id": (17, 11)},
  }
  def get_type(self):
      return self.get_bits(16,1)
  def get_numbits(self):
      return 12

class edacs_pkt(data_field):
  offset = 0
  types = {
             0: {"cmd": (0,8), "lcn": (8,4), "st1": (13,1), "st2": (14,1),
                 "st3": (15,1), "id": (16,12,edacs_id_data), "crc": (28,12)}
          }
  def get_type(self):
    return 0
  def get_numbits(self):
    return 40
