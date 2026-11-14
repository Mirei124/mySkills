use anyhow::{Context, Result, ensure};
use serde::Serialize;
use std::{
    collections::BTreeMap,
    fs::File,
    io::Write,
    os::fd::{AsFd, AsRawFd, FromRawFd},
    time::{Duration, Instant},
};
use wayland_client::{
    Connection, Dispatch, EventQueue, Proxy, QueueHandle, WEnum, delegate_noop,
    protocol::{wl_callback, wl_output, wl_registry, wl_seat},
};
use wayland_protocols::xdg::xdg_output::zv1::client::{zxdg_output_manager_v1, zxdg_output_v1};
use wayland_protocols_misc::zwp_virtual_keyboard_v1::client::{
    zwp_virtual_keyboard_manager_v1, zwp_virtual_keyboard_v1,
};
use wayland_protocols_wlr::virtual_pointer::v1::client::{
    zwlr_virtual_pointer_manager_v1, zwlr_virtual_pointer_v1,
};
use xkbcommon::xkb;

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct Output {
    pub name: String,
    pub position: (i32, i32),
    pub size: (i32, i32),
    pub scale: i32,
    pub transform: u32,
}
#[derive(Default)]
pub struct State {
    pub outputs: BTreeMap<u32, Output>,
    pub globals: BTreeMap<String, u32>,
    entries: BTreeMap<u32, (String, u32)>,
}
impl Dispatch<wl_registry::WlRegistry, ()> for State {
    fn event(
        state: &mut Self,
        _: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            wl_registry::Event::Global {
                name,
                interface,
                version,
            } => {
                state.entries.insert(name, (interface.clone(), version));
                state.globals.insert(interface, version);
            }
            wl_registry::Event::GlobalRemove { name } => {
                state.outputs.remove(&name);
                state.entries.remove(&name);
            }
            _ => {}
        }
    }
}
impl Dispatch<wl_output::WlOutput, u32> for State {
    fn event(
        state: &mut Self,
        _: &wl_output::WlOutput,
        event: wl_output::Event,
        id: &u32,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        let output = state.outputs.entry(*id).or_default();
        match event {
            wl_output::Event::Name { name } => output.name = name,
            wl_output::Event::Scale { factor } => output.scale = factor,
            wl_output::Event::Geometry { transform, .. } => {
                output.transform = match transform {
                    WEnum::Value(v) => v as u32,
                    WEnum::Unknown(v) => v,
                }
            }
            _ => {}
        }
    }
}
impl Dispatch<zxdg_output_v1::ZxdgOutputV1, u32> for State {
    fn event(
        state: &mut Self,
        _: &zxdg_output_v1::ZxdgOutputV1,
        event: zxdg_output_v1::Event,
        id: &u32,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        let output = state.outputs.entry(*id).or_default();
        match event {
            zxdg_output_v1::Event::LogicalPosition { x, y } => output.position = (x, y),
            zxdg_output_v1::Event::LogicalSize { width, height } => output.size = (width, height),
            zxdg_output_v1::Event::Name { name } => output.name = name,
            _ => {}
        }
    }
}
delegate_noop!(State: ignore wl_seat::WlSeat);
delegate_noop!(State: ignore zxdg_output_manager_v1::ZxdgOutputManagerV1);
delegate_noop!(State: ignore zwlr_virtual_pointer_manager_v1::ZwlrVirtualPointerManagerV1);
delegate_noop!(State: ignore zwlr_virtual_pointer_v1::ZwlrVirtualPointerV1);
delegate_noop!(State: ignore zwp_virtual_keyboard_manager_v1::ZwpVirtualKeyboardManagerV1);
delegate_noop!(State: ignore zwp_virtual_keyboard_v1::ZwpVirtualKeyboardV1);

pub struct Desktop {
    pub state: State,
    pub queue: EventQueue<State>,
    pub connection: Connection,
    pub handles: BTreeMap<u32, wl_output::WlOutput>,
    seat: Option<wl_seat::WlSeat>,
    pointer_manager: Option<zwlr_virtual_pointer_manager_v1::ZwlrVirtualPointerManagerV1>,
    keyboard_manager: Option<zwp_virtual_keyboard_manager_v1::ZwpVirtualKeyboardManagerV1>,
    _logical: Vec<zxdg_output_v1::ZxdgOutputV1>,
}
impl Desktop {
    pub fn connect() -> Result<Self> {
        let connection = Connection::connect_to_env().context("WAYLAND_UNAVAILABLE")?;
        Self::from_connection(connection)
    }
    fn from_connection(connection: Connection) -> Result<Self> {
        let mut queue = connection.new_event_queue::<State>();
        let qh = queue.handle();
        let registry = connection.display().get_registry(&qh, ());
        let mut state = State::default();
        roundtrip(&connection, &mut queue, &mut state, Duration::from_secs(3))?;
        let seats = state
            .entries
            .values()
            .filter(|(interface, _)| interface == "wl_seat")
            .count();
        ensure!(seats == 1, "AMBIGUOUS_SEAT");
        let seat = bind::<wl_seat::WlSeat>(&registry, &state, &qh, 1, 1);
        let pointer_manager = bind::<zwlr_virtual_pointer_manager_v1::ZwlrVirtualPointerManagerV1>(
            &registry, &state, &qh, 1, 2,
        );
        let keyboard_manager = bind::<zwp_virtual_keyboard_manager_v1::ZwpVirtualKeyboardManagerV1>(
            &registry, &state, &qh, 1, 1,
        );
        let manager =
            bind::<zxdg_output_manager_v1::ZxdgOutputManagerV1>(&registry, &state, &qh, 1, 3)
                .context("OUTPUT_GEOMETRY_UNAVAILABLE")?;
        let mut handles = BTreeMap::new();
        let mut logical = vec![];
        for (name, (interface, version)) in &state.entries {
            if interface != "wl_output" {
                continue;
            }
            let handle =
                registry.bind::<wl_output::WlOutput, _, _>(*name, (*version).min(4), &qh, *name);
            logical.push(manager.get_xdg_output(&handle, &qh, *name));
            handles.insert(*name, handle);
        }
        roundtrip(&connection, &mut queue, &mut state, Duration::from_secs(3))?;
        ensure!(!state.outputs.is_empty(), "OUTPUT_GEOMETRY_UNAVAILABLE");
        Ok(Self {
            state,
            queue,
            connection,
            handles,
            seat,
            pointer_manager,
            keyboard_manager,
            _logical: logical,
        })
    }
    pub fn refresh(&mut self) -> Result<()> {
        roundtrip(
            &self.connection,
            &mut self.queue,
            &mut self.state,
            Duration::from_secs(3),
        )
    }
    pub fn select(&self, name: Option<&str>) -> Result<(u32, Output)> {
        if name.is_none() {
            ensure!(
                self.state.outputs.len() == 1,
                "OUTPUT_CONFIRMATION_REQUIRED"
            );
        }
        let (id, output) = self
            .state
            .outputs
            .iter()
            .find(|(_, o)| name.is_none_or(|name| o.name == name))
            .context("UNKNOWN_OUTPUT")?;
        ensure!(
            !output.name.is_empty() && output.size.0 > 0 && output.size.1 > 0,
            "OUTPUT_GEOMETRY_UNAVAILABLE"
        );
        Ok((*id, output.clone()))
    }
}

pub struct Input {
    pub desktop: Desktop,
    pointer: zwlr_virtual_pointer_v1::ZwlrVirtualPointerV1,
    keyboard: zwp_virtual_keyboard_v1::ZwpVirtualKeyboardV1,
    keys: Vec<u32>,
    buttons: Vec<u32>,
    base: String,
    context: xkb::Context,
    epoch: Instant,
}
impl Input {
    pub fn new(desktop: Desktop, output: u32) -> Result<Self> {
        let manager = desktop
            .pointer_manager
            .as_ref()
            .context("PROTOCOL_UNAVAILABLE")?;
        let seat = desktop.seat.as_ref().context("PROTOCOL_UNAVAILABLE")?;
        let qh = desktop.queue.handle();
        let pointer = if manager.version() >= 2 {
            manager.create_virtual_pointer_with_output(
                Some(seat),
                Some(desktop.handles.get(&output).context("UNKNOWN_OUTPUT")?),
                &qh,
                (),
            )
        } else {
            ensure!(
                desktop.state.outputs.len() == 1,
                "OUTPUT_MAPPING_UNAVAILABLE"
            );
            manager.create_virtual_pointer(Some(seat), &qh, ())
        };
        let keyboard = desktop
            .keyboard_manager
            .as_ref()
            .context("PROTOCOL_UNAVAILABLE")?
            .create_virtual_keyboard(seat, &qh, ());
        let context = xkb::Context::new(xkb::CONTEXT_NO_FLAGS);
        let map = xkb::Keymap::new_from_names(
            &context,
            "",
            "",
            "us",
            "",
            None,
            xkb::KEYMAP_COMPILE_NO_FLAGS,
        )
        .context("KEYMAP_FAILED")?;
        let base = map.get_as_string(xkb::KEYMAP_FORMAT_TEXT_V1);
        let mut input = Self {
            desktop,
            pointer,
            keyboard,
            keys: vec![],
            buttons: vec![],
            base,
            context,
            epoch: Instant::now(),
        };
        input.upload(&input.base.clone())?;
        std::thread::sleep(Duration::from_millis(150));
        Ok(input)
    }
    fn timestamp(&self) -> u32 {
        self.epoch.elapsed().as_millis() as u32
    }
    fn sync(&mut self) -> Result<()> {
        self.pointer.frame();
        self.desktop.refresh()
    }
    fn upload(&mut self, text: &str) -> Result<()> {
        // SAFETY: memfd_create returns a new owned descriptor or -1; checked
        // before transferring its sole ownership to File.
        let fd = unsafe { libc::memfd_create(c"wf-keymap".as_ptr(), libc::MFD_CLOEXEC) };
        ensure!(fd >= 0, "KEYMAP_FD_FAILED");
        let mut file = unsafe { File::from_raw_fd(fd) };
        file.write_all(text.as_bytes())?;
        file.write_all(&[0])?;
        self.keyboard
            .keymap(1, file.as_fd(), u32::try_from(text.len() + 1)?);
        self.desktop.refresh()
    }
    pub fn motion(&mut self, x: u32, y: u32, width: u32, height: u32) -> Result<()> {
        ensure!(x < width && y < height, "COORDINATE_OUT_OF_BOUNDS");
        self.pointer
            .motion_absolute(self.timestamp(), x, y, width, height);
        self.sync()
    }
    pub fn button(&mut self, code: u32, pressed: bool) -> Result<()> {
        if pressed {
            if !self.buttons.contains(&code) {
                self.buttons.push(code);
            }
        } else {
            self.buttons.retain(|v| *v != code);
        }
        self.pointer.button(
            self.timestamp(),
            code,
            if pressed {
                wayland_client::protocol::wl_pointer::ButtonState::Pressed
            } else {
                wayland_client::protocol::wl_pointer::ButtonState::Released
            },
        );
        self.sync()
    }
    pub fn key(&mut self, code: u32, pressed: bool) -> Result<()> {
        if pressed {
            if !self.keys.contains(&code) {
                self.keys.push(code);
            }
        } else {
            self.keys.retain(|v| *v != code);
        }
        self.keyboard
            .key(self.timestamp(), code, u32::from(pressed));
        self.desktop.refresh()
    }
    pub fn modifiers(&mut self, mask: u32) -> Result<()> {
        self.keyboard.modifiers(mask, 0, 0, 0);
        self.desktop.refresh()
    }
    pub fn axis(&mut self, horizontal: bool, value: f64) -> Result<()> {
        use wayland_client::protocol::wl_pointer::Axis;
        self.pointer.axis(
            self.timestamp(),
            if horizontal {
                Axis::HorizontalScroll
            } else {
                Axis::VerticalScroll
            },
            value,
        );
        self.sync()
    }
    pub fn unicode(&mut self, character: char) -> Result<()> {
        let text = format!(
            "xkb_keymap {{ xkb_keycodes {{ include \"evdev+aliases(qwerty)\" }}; xkb_types {{ include \"complete\" }}; xkb_compatibility {{ include \"complete\" }}; xkb_symbols {{ include \"pc+us\" key <AC01> {{ [ U{:04X} ] }}; }}; }};",
            character as u32
        );
        let map = xkb::Keymap::new_from_string(
            &self.context,
            text,
            xkb::KEYMAP_FORMAT_TEXT_V1,
            xkb::KEYMAP_COMPILE_NO_FLAGS,
        )
        .context("KEYMAP_FAILED")?;
        self.upload(&map.get_as_string(xkb::KEYMAP_FORMAT_TEXT_V1))?;
        std::thread::sleep(Duration::from_millis(50));
        self.key(30, true)?;
        self.key(30, false)?;
        std::thread::sleep(Duration::from_millis(50));
        self.upload(&self.base.clone())
    }
    pub fn release(&mut self) -> Result<()> {
        for code in self.keys.clone() {
            self.key(code, false)?;
        }
        for code in self.buttons.clone() {
            self.button(code, false)?;
        }
        self.modifiers(0)?;
        self.sync()
    }
}
impl Drop for Input {
    fn drop(&mut self) {
        let _ = self.release();
        self.keyboard.destroy();
        self.pointer.destroy();
        let _ = self.desktop.connection.flush();
    }
}

/// Portal bootstrap device: never creates a virtual keyboard or uploads a keymap.
pub struct PointerOnly {
    desktop: Desktop,
    pointer: zwlr_virtual_pointer_v1::ZwlrVirtualPointerV1,
    held: bool,
    epoch: Instant,
}
impl PointerOnly {
    pub fn new(desktop: Desktop, output: u32) -> Result<Self> {
        let manager = desktop
            .pointer_manager
            .as_ref()
            .context("PROTOCOL_UNAVAILABLE")?;
        let seat = desktop.seat.as_ref().context("PROTOCOL_UNAVAILABLE")?;
        let queue = desktop.queue.handle();
        let pointer = if manager.version() >= 2 {
            manager.create_virtual_pointer_with_output(
                Some(seat),
                Some(desktop.handles.get(&output).context("UNKNOWN_OUTPUT")?),
                &queue,
                (),
            )
        } else {
            ensure!(
                desktop.state.outputs.len() == 1,
                "OUTPUT_MAPPING_UNAVAILABLE"
            );
            manager.create_virtual_pointer(Some(seat), &queue, ())
        };
        let mut device = Self {
            desktop,
            pointer,
            held: false,
            epoch: Instant::now(),
        };
        device.desktop.refresh()?;
        Ok(device)
    }
    pub fn motion(&mut self, x: u32, y: u32, width: u32, height: u32) -> Result<()> {
        ensure!(x < width && y < height, "COORDINATE_OUT_OF_BOUNDS");
        self.pointer
            .motion_absolute(self.epoch.elapsed().as_millis() as u32, x, y, width, height);
        self.pointer.frame();
        self.desktop.refresh()
    }
    pub fn button(&mut self, code: u32, pressed: bool) -> Result<()> {
        ensure!(code == 272, "UNSUPPORTED_BOOTSTRAP_BUTTON");
        self.held = pressed;
        self.pointer.button(
            self.epoch.elapsed().as_millis() as u32,
            code,
            if pressed {
                wayland_client::protocol::wl_pointer::ButtonState::Pressed
            } else {
                wayland_client::protocol::wl_pointer::ButtonState::Released
            },
        );
        self.pointer.frame();
        self.desktop.refresh()
    }
    pub fn release(&mut self) -> Result<()> {
        if self.held {
            self.button(272, false)?;
        }
        Ok(())
    }
}
impl Drop for PointerOnly {
    fn drop(&mut self) {
        let _ = self.release();
        self.pointer.destroy();
        let _ = self.desktop.connection.flush();
    }
}

fn bind<T: Proxy + 'static>(
    registry: &wl_registry::WlRegistry,
    state: &State,
    queue: &QueueHandle<State>,
    minimum: u32,
    maximum: u32,
) -> Option<T>
where
    State: Dispatch<T, ()>,
{
    state
        .entries
        .iter()
        .find(|(_, (interface, version))| interface == T::interface().name && *version >= minimum)
        .map(|(name, (_, version))| {
            registry.bind::<T, _, _>(*name, (*version).min(maximum), queue, ())
        })
}
impl Dispatch<wl_callback::WlCallback, std::sync::Arc<std::sync::atomic::AtomicBool>> for State {
    fn event(
        _: &mut Self,
        _: &wl_callback::WlCallback,
        event: wl_callback::Event,
        done: &std::sync::Arc<std::sync::atomic::AtomicBool>,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if matches!(event, wl_callback::Event::Done { .. }) {
            done.store(true, std::sync::atomic::Ordering::Release);
        }
    }
}
fn roundtrip(
    connection: &Connection,
    queue: &mut EventQueue<State>,
    state: &mut State,
    timeout: Duration,
) -> Result<()> {
    use std::sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    };
    let done = Arc::new(AtomicBool::new(false));
    let _callback = connection.display().sync(&queue.handle(), done.clone());
    let deadline = Instant::now() + timeout;
    loop {
        connection.flush()?;
        queue.dispatch_pending(state)?;
        if done.load(Ordering::Acquire) {
            return Ok(());
        }
        let remaining = deadline.saturating_duration_since(Instant::now());
        ensure!(!remaining.is_zero(), "WAYLAND_RESPONSE_TIMEOUT");
        if let Some(guard) = queue.prepare_read() {
            let mut fd = libc::pollfd {
                fd: connection.backend().poll_fd().as_raw_fd(),
                events: libc::POLLIN,
                revents: 0,
            };
            // SAFETY: a single initialized pollfd is borrowed for the bounded call.
            let count = unsafe {
                libc::poll(
                    &mut fd,
                    1,
                    remaining.as_millis().max(1).min(i32::MAX as u128) as i32,
                )
            };
            if count < 0 {
                let error = std::io::Error::last_os_error();
                if error.kind() == std::io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(error.into());
            }
            ensure!(count > 0, "WAYLAND_RESPONSE_TIMEOUT");
            guard.read()?;
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn silent_compositor_has_a_deadline() {
        let (client, _server) = std::os::unix::net::UnixStream::pair().unwrap();
        let connection = Connection::from_socket(client).unwrap();
        let mut queue = connection.new_event_queue::<State>();
        let mut state = State::default();
        let before = Instant::now();
        let error = roundtrip(
            &connection,
            &mut queue,
            &mut state,
            Duration::from_millis(20),
        )
        .unwrap_err();
        assert_eq!(error.to_string(), "WAYLAND_RESPONSE_TIMEOUT");
        assert!(before.elapsed() < Duration::from_secs(1));
    }
}
