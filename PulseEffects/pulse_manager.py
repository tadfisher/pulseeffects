# -*- coding: utf-8 -*-

from gi.repository import GObject, GLib

import PulseEffects.libpulse as p


class PulseManager(GObject.GObject):

    __gsignals__ = {
        'sink_inputs_changed': (GObject.SIGNAL_RUN_FIRST, None,
                                ())
    }

    def __init__(self):
        GObject.GObject.__init__(self)

        self.context_ok = False
        self.default_sink_name = ''
        self.sink_is_loaded = False
        self.sink_owner_module = -1
        self.sink_idx = -1
        self.sink_inputs = []

        self.app_blacklist = ['PulseEffects', 'pulseeffects', 'gsd-media-keys',
                              'GNOME Shell', 'libcanberra', 'gnome-pomodoro']

        self.media_blacklist = ['pulsesink probe']

        # wrapping callbacks
        self.ctx_cb = p.pa_context_notify_cb_t(self.context_status)
        self.server_info_cb = p.pa_server_info_cb_t(self.server_info)
        self.default_sink_info_cb = p.pa_sink_info_cb_t(self.default_sink_info)
        self.sink_info_cb = p.pa_sink_info_cb_t(self.sink_info)
        self.sink_input_info_cb = p.pa_sink_input_info_cb_t(
            self.sink_input_info)
        self.ctx_success_cb = p.pa_context_success_cb_t(self.ctx_success)
        self.subscribe_cb = p.pa_context_subscribe_cb_t(self.subscribe)

        # creating main loop and context
        self.main_loop = p.pa_threaded_mainloop_new()
        self.main_loop_api = p.pa_threaded_mainloop_get_api(self.main_loop)

        self.ctx = p.pa_context_new(self.main_loop_api, b'PulseEffects')

        p.pa_context_set_state_callback(self.ctx, self.ctx_cb, None)

        p.pa_context_connect(self.ctx, None, 0, None)

        p.pa_threaded_mainloop_start(self.main_loop)

        # waiting context

        while self.context_ok is False:
            pass

        # getting default sink name through server info

        o = p.pa_context_get_server_info(self.ctx, self.server_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

        # getting default sink rate through sink info. We set
        # module-null-sink to the same rate to reduce clock drift

        o = p.pa_context_get_sink_info_by_name(self.ctx,
                                               self.default_sink_name.encode(),
                                               self.default_sink_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

        # load source sink
        self.load_sink()

        # search sink inputs
        o = p.pa_context_get_sink_input_info_list(self.ctx,
                                                  self.sink_input_info_cb,
                                                  None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

        # subscribing to pulseaudio events
        p.pa_context_set_subscribe_callback(self.ctx, self.subscribe_cb,
                                            None)

        p.pa_context_subscribe(self.ctx,
                               p.PA_SUBSCRIPTION_MASK_SINK_INPUT,
                               self.ctx_success_cb, None)

    def context_status(self, context, user_data):
        state = p.pa_context_get_state(context)

        if state == p.PA_CONTEXT_READY:
            self.context_ok = True

        elif state == p.PA_CONTEXT_FAILED:
            print("Connection failed")

        elif state == p.PA_CONTEXT_TERMINATED:
            print("Connection terminated")

    def server_info(self, context, info, user_data):
        self.default_sink_name = info.contents.default_sink_name.decode()

    def default_sink_info(self, context, info, eol, user_data):
        if eol == 0:
            if info:
                self.default_sink_rate = info.contents.sample_spec.rate

    def sink_info(self, context, info, eol, user_data):
        if eol == -1:
            self.sink_is_loaded = False
        elif eol == 0:
            if info:
                self.sink_idx = info.contents.index
                self.sink_owner_module = info.contents.owner_module
        elif eol == 1:
            self.sink_is_loaded = True

    def sink_input_info(self, context, info, eol, user_data):
        if eol == -1:
            for s in self.sink_inputs:
                if s[0] == user_data:
                    self.sink_inputs.remove(s)

                    GLib.idle_add(self.emit, 'sink_inputs_changed')

                    break

        if info:
            idx = info.contents.index
            connected_sink_idx = info.contents.sink

            proplist = info.contents.proplist

            app_name = p.pa_proplist_gets(proplist, b'application.name')
            media_name = p.pa_proplist_gets(proplist, b'media.name')
            icon_name = p.pa_proplist_gets(proplist, b'application.icon_name')

            if not app_name:
                app_name = ''
            else:
                app_name = app_name.decode()

            if not media_name:
                media_name = ''
            else:
                media_name = media_name.decode()

            if not icon_name:
                icon_name = 'audio-x-generic-symbolic'
            else:
                icon_name = icon_name.decode()

            if (app_name not in self.app_blacklist and
                    media_name not in self.media_blacklist):
                connected = False

                if connected_sink_idx == self.sink_idx:
                    connected = True

                new_input = [idx, app_name, media_name, icon_name, connected]
                list_idx = 0
                have_this_input = False

                for s in self.sink_inputs:
                    if s[0] == idx:
                        have_this_input = True
                        break

                    list_idx = list_idx + 1

                if have_this_input:  # update sink input
                    self.sink_inputs[list_idx] = new_input
                else:
                    self.sink_inputs.append(new_input)

        if eol == 1:
            GLib.idle_add(self.emit, 'sink_inputs_changed')

    def load_sink_info(self):
        sink_name = 'PulseEffects'

        o = p.pa_context_get_sink_info_by_name(self.ctx, sink_name.encode(),
                                               self.sink_info_cb, None)

        while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
            pass

        p.pa_operation_unref(o)

    def load_sink(self):
        sink_name = 'PulseEffects'

        self.load_sink_info()

        if not self.sink_is_loaded:
            args = []

            sink_properties = 'device.description=\'PulseEffects\''
            sink_properties += 'device.class=\'sound\''

            args.append('sink_name=' + sink_name)
            args.append('sink_properties=' + sink_properties)
            args.append('channels=2')
            args.append('rate=' + str(self.default_sink_rate))

            argument = ' '.join(map(str, args)).encode('ascii')

            module = b'module-null-sink'

            def module_idx(context, idx, user_data):
                pass

            self.module_idx_cb = p.pa_context_index_cb_t(module_idx)

            o = p.pa_context_load_module(self.ctx, module, argument,
                                         self.module_idx_cb, None)

            while p.pa_operation_get_state(o) == p.PA_OPERATION_RUNNING:
                pass

            p.pa_operation_unref(o)

            self.load_sink_info()

    def grab_input(self, idx):
        p.pa_context_move_sink_input_by_index(self.ctx, idx,
                                              self.sink_idx,
                                              self.ctx_success_cb, None)

    def move_input_to_default_sink(self, idx):
        p.pa_context_move_sink_input_by_name(self.ctx, idx,
                                             self.default_sink_name.encode(),
                                             self.ctx_success_cb, None)

    def subscribe(self, context, event_value, idx, user_data):
        event_type = event_value & p.PA_SUBSCRIPTION_EVENT_TYPE_MASK

        user_data = None

        if event_type == p.PA_SUBSCRIPTION_EVENT_REMOVE:
            user_data = idx

        p.pa_context_get_sink_input_info(self.ctx, idx,
                                         self.sink_input_info_cb,
                                         user_data)

    def ctx_success(self, context, success, user_data):
        if not success:
            print("context operation failed!!")

    def unload_sink(self):
        self.load_sink_info()

        p.pa_context_unload_module(self.ctx, self.sink_owner_module,
                                   self.ctx_success_cb, None)
