# Lintel for SketchUp: Extensions > Lintel > Connect / disconnect. Give it a shortcut in
# Window > Preferences > Shortcuts (search "Lintel").
#
# SketchUp has no rooms or doors as objects, so Lintel reads four tags (like the Rhino plugin),
# with values in an attribute dictionary called "lintel":
#   Lintel Rooms   faces (floor outlines). Attributes: name, use (optional; guessed from the name).
#   Lintel Doors   component instances. Attributes: name, clear_width_mm, exit (true/false).
#                  Without clear_width_mm the width is the component's width.
#   Lintel Stairs  groups or components. Attributes: name, riser_mm, tread_mm, risers, width_mm, total_rise_mm.
#   Lintel Walls   edges.
# Element ids are persistent ids. Approved change sets run as one SketchUp operation, so one
# Edit > Undo reverses a Lintel edit. While connected Lintel re-checks every two seconds.
require 'json'
require 'net/http'
require 'uri'
require 'digest'

module Lintel
  TAGS = { 'Lintel Rooms' => 'room', 'Lintel Doors' => 'door', 'Lintel Stairs' => 'stair', 'Lintel Walls' => 'wall' }.freeze
  NUMERIC = %w[clear_width_mm riser_mm tread_mm risers width_mm total_rise_mm].freeze
  DICT = 'lintel'.freeze
  MM = 25.4             # SketchUp works in inches
  M2 = 0.00064516       # square inches -> square metres
  USES = [['corridor', %w[corridor hall passage circulation]], ['exam', %w[exam]], ['bedroom', %w[bedroom]],
          ['office', %w[office]], ['lobby', %w[lobby reception foyer]], ['wc', %w[wc toilet restroom bath]]].freeze

  # ---- the protocol (a Ruby port of hosts/lintel_client.py) ----------------

  def self.config
    path = File.join(Dir.home, '.lintel', 'config.json')
    File.exist?(path) ? JSON.parse(File.read(path)) : {}
  rescue JSON::ParserError
    {}
  end

  class Client
    attr_reader :url, :project

    def initialize(project, name)
      cfg = Lintel.config
      @url = (ENV['LINTEL_URL'] || cfg['url'] || 'http://127.0.0.1:8002').chomp('/')
      @token = ENV['LINTEL_TOKEN'] || cfg['token']
      raise 'No Lintel token. Create one in Lintel > Settings > Plugins and save it in ~/.lintel/config.json' unless @token
      @project, @name = project, name
    end

    def req(method, path, body = nil)
      uri = URI(@url + path)
      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = uri.scheme == 'https'
      http.open_timeout = http.read_timeout = 10
      r = (method == :get ? Net::HTTP::Get : Net::HTTP::Post).new(uri)
      r['Authorization'] = "Bearer #{@token}"
      r['Content-Type'] = 'application/json'
      r.body = JSON.generate(body) if body
      res = http.request(r)
      return nil if res.code == '404' && method == :get # first sync: the snapshot creates the project
      raise "Lintel answered HTTP #{res.code} #{res.body.to_s[0, 200]}" unless res.code.start_with?('2')
      res.body.to_s.empty? ? nil : JSON.parse(res.body)
    end

    def pending
      req(:get, "/api/plugin/pending?project=#{URI.encode_www_form_component(@project)}") || []
    end

    def push(elements)
      req(:post, '/api/plugin/snapshot', 'project' => @project, 'name' => @name, 'host' => 'sketchup', 'elements' => elements)
    end

    def report(id, ok, error)
      req(:post, '/api/plugin/result', 'changeset' => id, 'ok' => ok, 'error' => error, 'host' => 'sketchup')
    end
  end

  def self.same?(a, b)
    (Float(a) - Float(b)).abs < 0.05
  rescue ArgumentError, TypeError
    a == b
  end

  # Apply every op or none; refuse if the model drifted since the proposal.
  def self.apply(cs)
    model = Sketchup.active_model
    cs['ops'].each do |o|
      cur = get(o['element'], o['prop'])
      return [false, "element #{o['element']} no longer exists"] if cur == :missing
      unless o['from'].nil? || same?(cur, o['from'])
        return [false, "#{o['element']}.#{o['prop']} is now #{cur}, expected #{o['from']}; re-run checks"]
      end
    end
    model.start_operation("Lintel: #{cs['title']}", true)
    begin
      cs['ops'].each { |o| set(o['element'], o['prop'], o['to']) }
      model.commit_operation
      [true, nil]
    rescue StandardError => e
      model.abort_operation
      [false, "host error: #{e.message}"]
    end
  end

  # ---- reading the model ----------------------------------------------------

  def self.guess_use(name)
    n = " #{name.to_s.downcase} "
    hit = USES.find { |_, words| words.any? { |w| n.include?(w) } }
    hit ? hit[0] : ''
  end

  def self.attrs(e)
    out = {}
    (e.attribute_dictionary(DICT) || {}).each_pair do |k, v|
      out[k] = NUMERIC.include?(k) ? (Float(v) rescue v) : v
    end
    out['exit'] = %w[1 true yes y].include?(out['exit'].to_s.downcase) if out.key?('exit')
    out
  end

  def self.xscale(t)
    a = t.to_a
    Geom::Vector3d.new(a[0], a[1], a[2]).length.to_f
  end

  def self.door_width(e, a)
    a['clear_width_mm'].is_a?(Numeric) ? a['clear_width_mm'] : (e.definition.bounds.width * xscale(e.transformation) * MM).round(1)
  end

  def self.walk(entities, out)
    entities.each do |e|
      kind = e.respond_to?(:layer) && e.layer ? TAGS[e.layer.name] : nil
      out << [kind, e] if kind
      walk(e.entities, out) if e.is_a?(Sketchup::Group) && kind.nil?
    end
    out
  end

  def self.pt(p)
    [(p.x * MM).round(1), (p.y * MM).round(1)]
  end

  def self.snapshot
    els = []
    walk(Sketchup.active_model.entities, []).each do |kind, e|
      a = attrs(e)
      id = e.persistent_id.to_s
      name = a['name'] || (e.respond_to?(:name) && !e.name.to_s.empty? ? e.name : kind)
      case kind
      when 'room'
        next unless e.is_a?(Sketchup::Face)
        outline = e.outer_loop.vertices.map { |v| pt(v.position) }
        xs, ys = outline.map(&:first), outline.map(&:last)
        els << { 'id' => id, 'type' => 'room', 'geom' => { 'outline' => outline },
                 'props' => { 'name' => name, 'use' => a['use'] || guess_use(name), 'area_m2' => (e.area * M2).round(2),
                              'clear_width_mm' => [xs.max - xs.min, ys.max - ys.min].min.round(1) } }
      when 'door'
        next unless e.is_a?(Sketchup::ComponentInstance)
        els << { 'id' => id, 'type' => 'door', 'geom' => { 'location' => pt(e.transformation.origin) },
                 'props' => { 'name' => name, 'clear_width_mm' => door_width(e, a), 'exit' => a['exit'] || false } }
      when 'stair'
        props = { 'name' => name }
        %w[riser_mm tread_mm risers width_mm total_rise_mm].each { |k| props[k] = a[k] if a[k].is_a?(Numeric) }
        els << { 'id' => id, 'type' => 'stair', 'geom' => { 'location' => pt(e.bounds.center) }, 'props' => props }
      when 'wall'
        next unless e.is_a?(Sketchup::Edge)
        els << { 'id' => id, 'type' => 'wall', 'geom' => { 'start' => pt(e.start.position), 'end' => pt(e.end.position) },
                 'props' => { 'length_mm' => (e.length * MM).round(1) } }
      end
    end
    link_doors(els)
  end

  # Doors that don't list their rooms: any room whose outline passes within 300 mm.
  def self.link_doors(els)
    rooms = els.select { |e| e['type'] == 'room' }
    els.each do |d|
      next unless d['type'] == 'door'
      x, y = d['geom']['location']
      d['props']['rooms'] = rooms.select do |r|
        o = r['geom']['outline']
        o.each_index.any? do |i|
          (ax, ay), (bx, by) = o[i], o[(i + 1) % o.size]
          dx, dy = bx - ax, by - ay
          t = dx.zero? && dy.zero? ? 0 : [[((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy).to_f, 0].max, 1].min
          Math.hypot(x - (ax + t * dx), y - (ay + t * dy)) <= 300
        end
      end.map { |r| r['id'] }
    end
    els
  end

  def self.entity(id)
    Sketchup.active_model.find_entity_by_persistent_id(id.to_i)
  end

  def self.get(id, prop)
    el = snapshot.find { |e| e['id'] == id }
    el && el['props'].key?(prop) ? el['props'][prop] : :missing
  end

  def self.set(id, prop, value)
    e = entity(id) or raise "element #{id} no longer exists"
    if prop == 'clear_width_mm' && e.is_a?(Sketchup::ComponentInstance)
      old = door_width(e, attrs(e))
      e.transformation = e.transformation * Geom::Transformation.scaling(value.to_f / old, 1, 1) if old.positive?
    end
    if prop == 'riser_mm' && attrs(e)['total_rise_mm'].is_a?(Numeric) # more risers, each one lower
      total = attrs(e)['total_rise_mm']
      n = (total / value.to_f - 1e-9).ceil
      e.set_attribute(DICT, 'risers', n)
      value = (total / n).round(1)
    end
    e.set_attribute(DICT, prop, value)
    e.name = value.to_s if prop == 'name' && e.respond_to?(:name=)
  end

  # ---- the session -----------------------------------------------------------

  class Session
    attr_reader :client

    def initialize
      model = Sketchup.active_model
      key = model.get_attribute(DICT, 'project')
      unless key
        base = (model.title.empty? ? 'untitled' : model.title).downcase.gsub(/[^a-z0-9]+/, '-')
        key = "sketchup-#{base}-#{rand(36**6).to_s(36)}"
        model.set_attribute(DICT, 'project', key)
      end
      @client = Client.new(key, model.title.empty? ? 'Untitled SketchUp model' : model.title)
      @digest, @pushed_at, @known, @count = nil, 0, nil, 0
    end

    def tick
      applied = @client.pending.map do |cs|
        ok, err = Lintel.apply(cs)
        @client.report(cs['id'], ok, err)
        puts "Lintel: #{ok ? 'applied' : 'refused'} #{cs['title']} #{err}"
        cs['id']
      end
      els = Lintel.snapshot
      digest = Digest::SHA1.hexdigest(JSON.generate(els))
      return if digest == @digest && applied.empty? && Time.now.to_f - @pushed_at < 30
      out = @client.push(els) || {}
      @digest, @pushed_at, @count = digest, Time.now.to_f, out['issues'].to_i
      items = out['items'] || []
      if @known.nil?
        puts "Lintel: watching. #{@count} open issue#{@count == 1 ? '' : 's'}."
      else
        items.reject { |i| @known.include?(i['id']) }.first(5).each { |i| puts "Lintel: #{i['message']} (#{i['ref']})" }
      end
      @known = items.map { |i| i['id'] }
    rescue StandardError => e
      puts "Lintel: sync failed (#{e.message}); retrying"
    end

    def start
      tick
      @timer = UI.start_timer(2, true) { tick }
      @dialog = UI::HtmlDialog.new(dialog_title: 'Lintel', preferences_key: 'lintel.panel', width: 420, height: 720,
                                   style: UI::HtmlDialog::STYLE_UTILITY)
      @dialog.set_url("#{@client.url}/?panel=#{URI.encode_www_form_component(@client.project)}")
      @dialog.show
    end

    def stop
      UI.stop_timer(@timer) if @timer
      @dialog&.close
    end
  end

  def self.toggle
    if @session
      @session.stop
      @session = nil
      puts 'Lintel disconnected.'
    else
      @session = Session.new
      @session.start
      puts "Lintel connected: project #{@session.client.project}."
    end
  rescue StandardError => e
    UI.messagebox("Lintel couldn't connect: #{e.message}")
    @session = nil
  end

  def self.connected?
    !@session.nil?
  end

  unless file_loaded?(__FILE__)
    menu = UI.menu('Extensions').add_submenu('Lintel')
    item = menu.add_item('Connect / disconnect') { Lintel.toggle }
    menu.set_validation_proc(item) { Lintel.connected? ? MF_CHECKED : MF_UNCHECKED }
    file_loaded(__FILE__)
  end
end
