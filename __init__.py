# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

bl_info = {
"name": "Box deform",
"description": "Temporary deforming rectangle on selected GP points",
"author": "Samuel Bernou",
"version": (0, 2, 5),
"blender": (2, 83, 0),
"location": "Ctrl+T in GP object/edit/paint mode",
"warning": "",
"doc_url": "https://github.com/Pullusb/Box_deform",
"category": "3D View",
"support": 'COMMUNITY',
}

''' TODO
    # hard : Manage ESC during other modal ?
    # hard (optional) :  one big undo instead of multi undo ? (how to cancel other ops undo stack during modal...)

    # optional : option to reproject once finished
        # maybe with a modifier key

    # add option to place lattice according to object transform instead of view (no real need if stay GP only)
    
    # make a generic mesh handling (and add another shortcut for Mesh  edit)
    
    # whats the most proper way to add addon keymaps and expose to customisation in addon prefs...
    #  if in obj mode, consider all points (or even just get bbox if in object + local axis mode)
'''   

import bpy
import numpy as np


def location_to_region(worldcoords):
    from bpy_extras import view3d_utils
    return view3d_utils.location_3d_to_region_2d(bpy.context.region, bpy.context.space_data.region_3d, worldcoords)

def region_to_location(viewcoords, depthcoords):
    from bpy_extras import view3d_utils
    return view3d_utils.region_2d_to_location_3d(bpy.context.region, bpy.context.space_data.region_3d, viewcoords, depthcoords)

def assign_vg(obj, vg_name):
    ## create vertex group
    vg = obj.vertex_groups.get(vg_name)
    if vg:
        # remove to start clean
        obj.vertex_groups.remove(vg)
    vg = obj.vertex_groups.new(name=vg_name)
    bpy.ops.gpencil.vertex_group_assign()
    return vg

def view_cage(obj):

    lattice_interp = get_addon_prefs().default_deform_type

    gp = obj.data
    gpl = gp.layers

    coords = []
    initial_mode = bpy.context.mode

    ## get points
    if bpy.context.mode == 'EDIT_GPENCIL':
        for l in gpl:
            if l.lock or l.hide or not l.active_frame:#or len(l.frames)
                continue
            if gp.use_multiedit:
                target_frames = [f for f in l.frames if f.select]
            else:
                target_frames = [l.active_frame]
            
            for f in target_frames:
                for s in f.strokes:
                    if not s.select:
                        continue
                    for p in s.points:
                        if p.select:
                            # get real location
                            coords.append(obj.matrix_world @ p.co)

    elif bpy.context.mode == 'OBJECT':#object mode -> all points
        for l in gpl:# if l.hide:continue# only visible ? (might break things)
            if not len(l.frames):
                continue#skip frameless layer
            for s in l.active_frame.strokes:
                for p in s.points:
                    coords.append(obj.matrix_world @ p.co)
    
    elif bpy.context.mode == 'PAINT_GPENCIL':
        # get last stroke points coordinated
        if not gpl.active or not gpl.active.active_frame:
            return 'No frame to deform'

        if not len(gpl.active.active_frame.strokes):
            return 'No stroke found to deform'
        
        paint_id = -1
        if bpy.context.scene.tool_settings.use_gpencil_draw_onback:
            paint_id = 0
        coords = [obj.matrix_world @ p.co for p in gpl.active.active_frame.strokes[paint_id].points]
    
    else:
        return 'Wrong mode!'

    if not coords:
        ## maybe silent return instead (need special str code to manage errorless return)
        return 'No points found!'

    if bpy.context.mode in ('EDIT_GPENCIL', 'PAINT_GPENCIL') and len(coords) < 2:
        # Dont block object mod
        return 'Less than two point selected'

    vg_name = 'lattice_cage_deform_group'

    if bpy.context.mode == 'EDIT_GPENCIL':
        vg = assign_vg(obj, vg_name)
    
    if bpy.context.mode == 'PAINT_GPENCIL':
        # points cannot be assign to API yet(ugly and slow workaround but only way)
        # -> https://developer.blender.org/T56280 so, hop'in'ops !
        
        # store selection and deselect all
        plist = []
        for s in gpl.active.active_frame.strokes:
            for p in s.points:
                plist.append([p, p.select])
                p.select = False
        
        # select
        ## foreach_set does not update
        # gpl.active.active_frame.strokes[paint_id].points.foreach_set('select', [True]*len(gpl.active.active_frame.strokes[paint_id].points))
        for p in gpl.active.active_frame.strokes[paint_id].points:
            p.select = True
        
        # assign
        bpy.ops.object.mode_set(mode='EDIT_GPENCIL')
        vg = assign_vg(obj, vg_name)

        # restore
        for pl in plist:
            pl[0].select = pl[1]
        

    ## View axis Mode ---

    ## get view coordinate of all points
    coords2D = [location_to_region(co) for co in coords]

    # find centroid for depth (or more economic, use obj origin...)
    centroid = np.mean(coords, axis=0)

    # not a mean ! a mean of extreme ! centroid2d = np.mean(coords2D, axis=0)
    all_x, all_y = np.array(coords2D)[:, 0], np.array(coords2D)[:, 1]
    min_x, min_y = np.min(all_x), np.min(all_y)
    max_x, max_y = np.max(all_x), np.max(all_y)

    width = (max_x - min_x)
    height = (max_y - min_y)
    center_x = min_x + (width/2)
    center_y = min_y + (height/2)

    centroid2d = (center_x,center_y)
    center = region_to_location(centroid2d, centroid)
    # bpy.context.scene.cursor.location = center#Dbg


    #corner Bottom-left to Bottom-right
    x0 = region_to_location((min_x, min_y), centroid)
    x1 = region_to_location((max_x, min_y), centroid)
    x_worldsize = (x0 - x1).length

    #corner Bottom-left to top-left
    y0 = region_to_location((min_x, min_y), centroid)
    y1 = region_to_location((min_x, max_y), centroid)
    y_worldsize = (y0 - y1).length

    ## in case of 3

    lattice_name = 'lattice_cage_deform'
    # cleaning
    cage = bpy.data.objects.get(lattice_name)
    if cage:
        bpy.data.objects.remove(cage)

    lattice = bpy.data.lattices.get(lattice_name)
    if lattice:
        bpy.data.lattices.remove(lattice)

    # create lattice object
    lattice = bpy.data.lattices.new(lattice_name)
    cage = bpy.data.objects.new(lattice_name, lattice)
    cage.show_in_front = True

    ## Master (root) collection
    bpy.context.scene.collection.objects.link(cage)

    # spawn cage and align it to view (Again ! align something to a vector !!! argg)

    r3d = bpy.context.space_data.region_3d
    viewmat = r3d.view_matrix

    cage.matrix_world = viewmat.inverted()
    cage.scale = (x_worldsize, y_worldsize, 1)
    ## Z aligned in view direction (need minus X 90 degree to be aligned FRONT)
    # cage.rotation_euler.x -= radians(90)
    # cage.scale = (x_worldsize, 1, y_worldsize)
    cage.location = center

    lattice.points_u = 2
    lattice.points_v = 2
    lattice.points_w = 1

    lattice.interpolation_type_u = lattice_interp#'KEY_LINEAR'-'KEY_BSPLINE'
    lattice.interpolation_type_v = lattice_interp#'KEY_LINEAR'-'KEY_BSPLINE'
    lattice.interpolation_type_w = lattice_interp#'KEY_LINEAR'-'KEY_BSPLINE'

    mod = obj.grease_pencil_modifiers.new('tmp_lattice', 'GP_LATTICE')

    # move to top if modifiers exists
    for _ in range(len(obj.grease_pencil_modifiers)):
        bpy.ops.object.gpencil_modifier_move_up(modifier='tmp_lattice')

    mod.object = cage

    if initial_mode == 'PAINT_GPENCIL':
        mod.layer = gpl.active.info

    # note : if initial was Paint, changed to Edit
    #        so vertex attribution is valid even for paint
    if bpy.context.mode == 'EDIT_GPENCIL':
        mod.vertex_group = vg.name

    #Go in object mode if not already
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Store name of deformed object in case of 'revive modal' 
    cage.vertex_groups.new(name=obj.name)

    ## select and make cage active
    # cage.select_set(True)
    bpy.context.view_layer.objects.active = cage
    obj.select_set(False)#deselect GP object
    bpy.ops.object.mode_set(mode='EDIT')# go in lattice edit mode
    bpy.ops.lattice.select_all(action='SELECT')# select all points

    ## Eventually change tool mode to tweak for direct point editing (reset after before leaving)
    bpy.ops.wm.tool_set_by_id(name="builtin.select")# Tweaktoolcode
    return cage


def back_to_obj(obj, gp_mode, org_lattice_toolset, context):
    if context.mode == 'EDIT_LATTICE' and org_lattice_toolset:# Tweaktoolcode - restore the active tool used by lattice edit..
        bpy.ops.wm.tool_set_by_id(name = org_lattice_toolset)# Tweaktoolcode
    
    # gp object active and selected
    bpy.ops.object.mode_set(mode='OBJECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def delete_cage(cage):
    lattice = cage.data
    bpy.data.objects.remove(cage)
    bpy.data.lattices.remove(lattice)

def apply_cage(gp_obj, cage):
    mod = gp_obj.grease_pencil_modifiers.get('tmp_lattice')
    if mod:
        bpy.ops.object.gpencil_modifier_apply(apply_as='DATA', modifier=mod.name)
    else:
        print('tmp_lattice modifier not found to apply...')

    delete_cage(cage)

def cancel_cage(gp_obj, cage):
    #remove modifier
    mod = gp_obj.grease_pencil_modifiers.get('tmp_lattice')
    if mod:
        gp_obj.grease_pencil_modifiers.remove(mod)
    else:
        print('tmp_lattice modifier not found to remove...')
    
    delete_cage(cage)
    

class BOXD_OT_lattice_gp_deform(bpy.types.Operator):
    """Create a lattice to use as transform"""
    bl_idname = "gp.box_deform"
    bl_label = "Box deform"
    bl_description = "Use lattice for free box transforms on grease pencil points"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.object is not None and context.object.type in ('GPENCIL','LATTICE')

    # local variable
    tab_press_ct = 0

    def modal(self, context, event):
        display_text = f"Deform Cage size: {self.lat.points_u}x{self.lat.points_v} (1-9 or ctrl + ←→↑↓])  | \
mode (M) : {'Linear' if self.lat.interpolation_type_u == 'KEY_LINEAR' else 'Spline'} | \
valid:Spacebar/Enter/Tab, cancel:Del/Backspace"
        context.area.header_text_set(display_text)
        # context.area.tag_redraw() #?

        #tester
        # if event.type not in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE'}: print('key:', event.type, 'value:', event.value)

        ## Handle ctrl+Z
        if event.type in {'Z'} and event.value == 'PRESS' and event.ctrl:
            ## Disable (capture key)
            return {"RUNNING_MODAL"}
            ## Not found how possible to find modal start point in undo stack to 
            # print('ops list', context.window_manager.operators.keys())
            # if context.window_manager.operators:#can be empty
            #     print('\nlast name', context.window_manager.operators[-1].name)

        # auto interpo
        if self.auto_interp:
            if event.type in {'TWO', 'THREE', 'FOUR', 'FIVE', 'SIX', 'SEVEN', 'EIGHT', 'NINE', 'ZERO',} and event.value == 'PRESS':
                self.set_lattice_interp('KEY_BSPLINE')
            if event.type in {'DOWN_ARROW', "UP_ARROW", "RIGHT_ARROW", "LEFT_ARROW"} and event.value == 'PRESS' and event.ctrl:
                # not after actual change, can't check "self.lat.points_u == self.lat.points_v == 2"
                self.set_lattice_interp('KEY_BSPLINE')
            if event.type in {'ONE'} and event.value == 'PRESS':
                self.set_lattice_interp('KEY_LINEAR')

        # Single keys
        if event.type in {'H'}:
            if event.value == 'PRESS':
                self.report({'INFO'}, "Don't try to hide it ! it's no use ! ahah ;)")
                # print("Don't try to hide it ! it's no use ! ahaha")
                return {"RUNNING_MODAL"}
        
        if event.type in {'ONE'} and event.value == 'PRESS':# , 'NUMPAD_1'
            self.lat.points_u = self.lat.points_v = 2
            return {"RUNNING_MODAL"}

        if event.type in {'TWO'} and event.value == 'PRESS':# , 'NUMPAD_2'
            self.lat.points_u = self.lat.points_v = 3
            return {"RUNNING_MODAL"}

        if event.type in {'THREE'} and event.value == 'PRESS':# , 'NUMPAD_3'
            self.lat.points_u = self.lat.points_v = 4
            return {"RUNNING_MODAL"}

        if event.type in {'FOUR'} and event.value == 'PRESS':# , 'NUMPAD_4'
            self.lat.points_u = self.lat.points_v = 5
            return {"RUNNING_MODAL"}

        if event.type in {'FIVE'} and event.value == 'PRESS':# , 'NUMPAD_5'
            self.lat.points_u = self.lat.points_v = 6
            return {"RUNNING_MODAL"}

        if event.type in {'SIX'} and event.value == 'PRESS':# , 'NUMPAD_6'
            self.lat.points_u = self.lat.points_v = 7
            return {"RUNNING_MODAL"}

        if event.type in {'SEVEN'} and event.value == 'PRESS':# , 'NUMPAD_7'
            self.lat.points_u = self.lat.points_v = 8
            return {"RUNNING_MODAL"}

        if event.type in {'EIGHT'} and event.value == 'PRESS':# , 'NUMPAD_8'
            self.lat.points_u = self.lat.points_v = 9
            return {"RUNNING_MODAL"}

        if event.type in {'NINE'} and event.value == 'PRESS':# , 'NUMPAD_9'
            self.lat.points_u = self.lat.points_v = 10
            return {"RUNNING_MODAL"}

        if event.type in {'ZERO'} and event.value == 'PRESS':# , 'NUMPAD_0'
            self.lat.points_u = 2
            self.lat.points_v = 1
            return {"RUNNING_MODAL"}
        
        if event.type in {'RIGHT_ARROW'} and event.value == 'PRESS' and event.ctrl:
            if self.lat.points_u < 20:
                self.lat.points_u += 1 
            return {"RUNNING_MODAL"}

        if event.type in {'LEFT_ARROW'} and event.value == 'PRESS' and event.ctrl:
            if self.lat.points_u > 1:
                self.lat.points_u -= 1 
            return {"RUNNING_MODAL"}

        if event.type in {'UP_ARROW'} and event.value == 'PRESS' and event.ctrl:
            if self.lat.points_v < 20:
                self.lat.points_v += 1 
            return {"RUNNING_MODAL"}

        if event.type in {'DOWN_ARROW'} and event.value == 'PRESS' and event.ctrl:
            if self.lat.points_v > 1:
                self.lat.points_v -= 1 
            return {"RUNNING_MODAL"}

        # change modes
        if event.type in {'M'} and event.value == 'PRESS':
            self.auto_interp = False
            interp = 'KEY_BSPLINE' if self.lat.interpolation_type_u == 'KEY_LINEAR' else 'KEY_LINEAR'
            self.set_lattice_interp(interp)
            return {"RUNNING_MODAL"}

        # Valid
        if event.type in {'RET', 'SPACE'}:
            if event.value == 'PRESS':
                #bpy.ops.ed.flush_edits()# TODO: find a way to get rid of undo-registered lattices tweaks
                self.restore_prefs(context)
                back_to_obj(self.gp_obj, self.gp_mode, self.org_lattice_toolset, context)
                apply_cage(self.gp_obj, self.cage)#must be in object mode
                
                # back to original mode 
                if self.gp_mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode=self.gp_mode)

                context.area.header_text_set(None)#reset header

                return {'FINISHED'}
        
        # Abort ---
        # One Warning for Tab cancellation.
        if event.type == 'TAB' and event.value == 'PRESS':
            self.tab_press_ct += 1
            if self.tab_press_ct < 2:
                self.report({'WARNING'}, "Pressing TAB again will Cancel")
                return {"RUNNING_MODAL"}

        if event.type in {'T'} and event.value == 'PRESS' and event.ctrl:
            # Retyped same shortcut...
            self.cancel(context)
            return {'CANCELLED'}

        if event.type in {'DEL', 'BACK_SPACE'} or self.tab_press_ct >= 2:#'ESC',
            self.cancel(context)
            return {'CANCELLED'}

        return {'PASS_THROUGH'}

    def set_lattice_interp(self, interp):
        self.lat.interpolation_type_u = self.lat.interpolation_type_v = self.lat.interpolation_type_w = interp

    def cancel(self, context):
        self.restore_prefs(context)
        back_to_obj(self.gp_obj, self.gp_mode, self.org_lattice_toolset, context)
        cancel_cage(self.gp_obj, self.cage)
        context.area.header_text_set(None)     
        if self.gp_mode != 'OBJECT':
            bpy.ops.object.mode_set(mode=self.gp_mode)

    def store_prefs(self, context):
        # store_valierables <-< preferences
        self.use_drag_immediately = context.preferences.inputs.use_drag_immediately 
        self.drag_threshold_mouse = context.preferences.inputs.drag_threshold_mouse 
        self.drag_threshold_tablet = context.preferences.inputs.drag_threshold_tablet
        self.use_overlays = context.space_data.overlay.show_overlays

    def restore_prefs(self, context):
        # preferences <-< store_valierables
        context.preferences.inputs.use_drag_immediately = self.use_drag_immediately
        context.preferences.inputs.drag_threshold_mouse = self.drag_threshold_mouse
        context.preferences.inputs.drag_threshold_tablet = self.drag_threshold_tablet
        context.space_data.overlay.show_overlays = self.use_overlays
    
    def set_prefs(self, context):
        context.preferences.inputs.use_drag_immediately = True
        context.preferences.inputs.drag_threshold_mouse = 1
        context.preferences.inputs.drag_threshold_tablet = 3
        context.space_data.overlay.show_overlays = True

    def invoke(self, context, event):
        ## Restrict to 3D view
        if context.area.type != 'VIEW_3D':
            self.report({'WARNING'}, "View3D not found, cannot run operator")
            return {'CANCELLED'}

        if not context.object:#do it in poll ?
            self.report({'ERROR'}, "No active objects found")
            return {'CANCELLED'}

        self.prefs = get_addon_prefs()#get_prefs
        self.org_lattice_toolset = None
        self.gp_mode = 'EDIT_GPENCIL'

        # --- special Case of lattice revive modal, just after ctrl+Z back into lattice with modal stopped
        if context.mode == 'EDIT_LATTICE' and context.object.name == 'lattice_cage_deform' and len(context.object.vertex_groups):
            self.gp_obj = context.scene.objects.get(context.object.vertex_groups[0].name)
            if not self.gp_obj:
                self.report({'ERROR'}, "/!\\ Box Deform : Cannot find object to target")
                return {'CANCELLED'}
            if not self.gp_obj.grease_pencil_modifiers.get('tmp_lattice'):
                self.report({'ERROR'}, "/!\\ No 'tmp_lattice' modifiers on GP object")
                return {'CANCELLED'}
            self.cage = context.object
            self.lat = self.cage.data
            self.set_prefs(context)

            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}

        if context.object.type != 'GPENCIL':
            # self.report({'ERROR'}, "Works only on gpencil objects")
            ## silent return 
            return {'CANCELLED'}

        #paint need VG workaround. object need good shortcut
        if context.mode not in ('EDIT_GPENCIL', 'OBJECT', 'PAINT_GPENCIL'):
            # self.report({'WARNING'}, "Works only in following GPencil modes: edit")# ERROR
            ## silent return 
            return {'CANCELLED'}

        # bpy.ops.ed.undo_push(message="Box deform step")#don't work as expected (+ might be obsolete)
        # https://developer.blender.org/D6147 <- undo forget 

        self.gp_obj = context.object
        # Clean potential failed previous job (delete tmp lattice)
        mod = self.gp_obj.grease_pencil_modifiers.get('tmp_lattice')
        if mod:
            print('Deleted remaining lattice modifiers')
            self.gp_obj.grease_pencil_modifiers.remove(mod)

        phantom_obj = context.scene.objects.get('lattice_cage_deform')
        if phantom_obj:
            print('deleted remaining lattice object')
            delete_cage(phantom_obj)

        if [m for m in self.gp_obj.grease_pencil_modifiers if m.type == 'GP_LATTICE']:
            self.report({'ERROR'}, "Beg your pardon, but your object already has a lattice modifier (it happens that GP object can only have one lattice modifiers).\nDevotely yours, Alfred.")#maybe not paint for now
            return {'CANCELLED'}
        

        self.gp_mode = context.mode#store mode for restore
        
        # All good, create lattice and start modal

        # Create lattice (and switch to lattice edit) ----
        self.cage = view_cage(self.gp_obj)
        if isinstance(self.cage, str):#error, cage not created, display error
            self.report({'ERROR'}, self.cage)
            return {'CANCELLED'}
        
        self.lat = self.cage.data

        ## usability toggles
        if self.prefs.use_clic_drag:#Store the active tool since we will change it
            self.org_lattice_toolset = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False).idname# Tweaktoolcode    
        
        self.auto_interp = self.prefs.auto_swap_deform_type
        #store (scene properties needed in case of ctrlZ revival)
        self.store_prefs(context)
        self.set_prefs(context)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


## --- PREFS

class BOXD_addon_prefs(bpy.types.AddonPreferences):
    bl_idname = __name__

    pref_tabs : bpy.props.EnumProperty(
        items=(('PREF', "Preferences", "Change some preferences of the modal"),
               ('TUTO', "Tutorial", "How to use the tool"),
               # ('KEYMAP', "Keymap", "customise the default keymap"),
               ),
               default='PREF')

    # --- props
    use_clic_drag : bpy.props.BoolProperty(
        name='Use click drag directly on points',
        description="Change the active tool to 'tweak' during modal, Allow to direct clic-drag points of the box",
        default=True)
    
    default_deform_type : bpy.props.EnumProperty(
        items=(('KEY_LINEAR', "Linear (perspective mode)", "Use Linear interpolation, like corner deform / perspective tools of classic 2D", 'IPO_LINEAR',0),
               ('KEY_BSPLINE', "Spline (smooth deform)", "Use spline interpolation transformation\nBest when lattice is subdivided", 'IPO_CIRC',1),
               ),
               name='Starting interpolation', default='KEY_LINEAR', description='Choose default interpolation when entering mode')

    auto_swap_deform_type : bpy.props.BoolProperty(
        name='Auto swap interpolation mode',
        description="Automatically set interpolation to 'spline' when subdividing lattice\n Back to 'linear' when",
        default=True)

    def draw(self, context):
            layout = self.layout
            # layout.use_property_split = True
            row= layout.row(align=True)
            row.prop(self, "pref_tabs", expand=True)

            if self.pref_tabs == 'PREF':
                layout.label(text='Some text')

                # display the bool prop
                layout.prop(self, "use_clic_drag")
                layout.separator()
                layout.label(text="Deformer type can be changed during modal with 'M' key, this settings is for default behavior", icon='INFO')
                layout.prop(self, "default_deform_type")

                layout.prop(self, "auto_swap_deform_type")
                layout.label(text="Once 'M' is hit, auto swap is desactivated to stay in your chosen mode", icon='INFO')

            if self.pref_tabs == 'TUTO':

                #**Behavior from context mode**
                col = layout.column()
                col.label(text="Usage:", icon='MOD_LATTICE')
                col.label(text="Use the shortcut 'Ctrl+T' in available modes (listed below)")
                col.label(text="The lattice box is generated facing your view (be sure to face canvas if you want to stay on it)")
                col.label(text="Use shortcuts below to deform(a help will be displayed in the topbar)")

                col.separator()
                col.label(text="Shortcuts:", icon='HAND')
                col.label(text="Spacebar / Enter : Confirm")
                col.label(text="Delete / Backspace / Tab(twice) / ctrl+T : Cancel")
                col.label(text="M : Toggle between Linear and Spline mode at any moment")
                col.label(text="1-9 top row number : Subdivide the box")
                col.label(text="Ctrl + arrows-keys : Subdivide the box incrementally in individual X/Y axis")

                col.separator()
                col.label(text="Modes and deformation target:", icon='PIVOT_BOUNDBOX')
                col.label(text="- Object mode : The whole GP object is deformed")
                col.label(text="- GPencil Edit mode : Deform Selected points")
                col.label(text="- Gpencil Paint : Deform last Strokes")
                # col.label(text="- Lattice edit : Revive the modal after a ctrl+Z")

                col.separator()
                col.label(text="Notes:", icon='TEXT')
                col.label(text="If you return in box deform after applying (with a ctrl+Z), you need to hit 'Ctrl+T' again to revive the modal.")

                col.label(text="A cancel warning will be displayed the first time you hit Tab")

                #col.operator("wm.url_open", text="Demo").url = "DEMO URL"



def get_addon_prefs():
    import os
    addon_name = os.path.splitext(__name__)[0]
    preferences = bpy.context.preferences
    addon_prefs = preferences.addons[addon_name].preferences
    return (addon_prefs)

## --- KEYMAP

addon_keymaps = []
def register_keymaps():
    addon = bpy.context.window_manager.keyconfigs.addon

    km = addon.keymaps.new(name = "Grease Pencil", space_type = "EMPTY", region_type='WINDOW')
    # km = addon.keymaps.new(name = "Grease Pencil Stroke Edit Mode", space_type = "EMPTY", region_type='WINDOW')
    kmi = km.keymap_items.new("gp.box_deform", type ='T', value = "PRESS", ctrl = True)
    kmi.repeat = False
    addon_keymaps.append(km)

    # km = addon.keymaps.new(name = "Object Mode", space_type = "VIEW_3D", region_type='WINDOW')
    # kmi = km.keymap_items.new("gp.box_deform", type ='T', value = "PRESS", ctrl = True)
    # kmi.repeat = False
    # addon_keymaps.append(km)

    # km = addon.keymaps.new(name = "Lattice", space_type = "EMPTY", region_type='WINDOW')
    # kmi = km.keymap_items.new("gp.box_deform", type ='T', value = "PRESS", ctrl = True)
    # kmi.repeat = False
    # addon_keymaps.append(km)

def unregister_keymaps():
    for km in addon_keymaps:
        for kmi in km.keymap_items:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()


### --- REGISTER ---

classes = (
BOXD_addon_prefs,
BOXD_OT_lattice_gp_deform,
)

def register():
    if bpy.app.background:
        return
    for cls in classes:
        bpy.utils.register_class(cls)
    register_keymaps()

def unregister():
    if bpy.app.background:
        return
    unregister_keymaps()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()


"""     
redister :
BOXD_PGT_store_default,

# old in modal store
    def store_prefs(self, context):
        # store_valierables <-< preferences
        context.scene.boxdeform.use_drag_immediately = context.preferences.inputs.use_drag_immediately 
        context.scene.boxdeform.drag_threshold_mouse = context.preferences.inputs.drag_threshold_mouse 
        context.scene.boxdeform.drag_threshold_tablet = context.preferences.inputs.drag_threshold_tablet 
        self.use_overlays = context.space_data.overlay.show_overlays

    def restore_prefs(self, context):
        # preferences <-< store_valierables
        context.preferences.inputs.use_drag_immediately = context.scene.boxdeform.use_drag_immediately
        context.preferences.inputs.drag_threshold_mouse = context.scene.boxdeform.drag_threshold_mouse
        context.preferences.inputs.drag_threshold_tablet = context.scene.boxdeform.drag_threshold_tablet
        context.space_data.overlay.show_overlays = self.use_overlays

## --- PROPERTIES (store prefs)

class BOXD_PGT_store_default(bpy.types.PropertyGroup) :
    # use_drag_immediately - bool (default False)
    # drag_threshold_mouse - int (px) default 3
    # drag_threshold_tablet - int (px) default 10
    use_drag_immediately : bpy.props.BoolProperty(
        name="Realease Confirms", description="settings in mouse input", default=False)

    drag_threshold_mouse : bpy.props.IntProperty(
        name="Mouse Drag Threshold", description="settings in mouse input", default=3)

    drag_threshold_tablet : bpy.props.IntProperty(
        name="Tablet Drag Threshold", description="settings in mouse input", default=10)

register/unregister :
    bpy.types.Scene.boxdeform = bpy.props.PointerProperty(type = BOXD_PGT_store_default)
    del bpy.types.Scene.boxdeform
"""