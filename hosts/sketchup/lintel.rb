# Lintel for SketchUp (2020 and later). Copy this file and the lintel/ folder into SketchUp's
# Plugins folder (Window > Extension Manager shows it once SketchUp restarts), or zip both as an .rbz.
require 'sketchup.rb'
require 'extensions.rb'

module Lintel
  EXTENSION = SketchupExtension.new('Lintel', File.join(File.dirname(__FILE__), 'lintel', 'main'))
  EXTENSION.description = 'Live rule checks against your office standards; approved fixes applied as one undo step.'
  EXTENSION.version = '0.2.0'
  EXTENSION.creator = 'Lintel'
  Sketchup.register_extension(EXTENSION, true)
end
