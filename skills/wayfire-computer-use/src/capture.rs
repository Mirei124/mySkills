use anyhow::{Context, Result, bail, ensure};
use pipewire::{self as pw, properties::properties, spa};
use std::{
    fs::OpenOptions,
    io::BufWriter,
    os::{fd::OwnedFd, unix::fs::OpenOptionsExt},
    path::Path,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

#[derive(Clone)]
struct Frame {
    width: u32,
    height: u32,
    pixels: Vec<u8>,
    received: Instant,
    pts: Option<i64>,
}
#[derive(Default)]
struct Shared {
    frame: Option<Frame>,
    error: Option<String>,
}
pub struct Capture {
    shared: Arc<Mutex<Shared>>,
    stop: Arc<AtomicBool>,
    thread: Option<thread::JoinHandle<()>>,
}
struct Data {
    format: spa::param::video::VideoInfoRaw,
    shared: Arc<Mutex<Shared>>,
}
pub fn monotonic_ns() -> i64 {
    let mut time = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    // SAFETY: a writable timespec is provided for a constant valid clock ID.
    if unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut time) } != 0 {
        return -1;
    }
    time.tv_sec
        .saturating_mul(1_000_000_000)
        .saturating_add(time.tv_nsec)
}
impl Capture {
    pub fn new(fd: OwnedFd, node: u32) -> Self {
        let shared = Arc::new(Mutex::new(Shared::default()));
        let stop = Arc::new(AtomicBool::new(false));
        let worker_shared = shared.clone();
        let worker_stop = stop.clone();
        let thread = thread::spawn(move || {
            if let Err(error) = run(fd, node, worker_shared.clone(), worker_stop) {
                worker_shared.lock().unwrap().error = Some(error.to_string());
            }
        });
        Self {
            shared,
            stop,
            thread: Some(thread),
        }
    }
    pub fn observe(&self, path: &Path, after: i64) -> Result<(u32, u32)> {
        let started = Instant::now();
        loop {
            let frame = {
                let state = self.shared.lock().unwrap();
                if let Some(error) = &state.error {
                    bail!("{error}");
                }
                state.frame.clone()
            };
            if let Some(frame) = frame {
                if frame.received >= started {
                    let pts = frame.pts.context("FRAME_TIMESTAMP_UNAVAILABLE")?;
                    if pts >= after {
                        write_png(path, frame.width, frame.height, &frame.pixels)?;
                        return Ok((frame.width, frame.height));
                    }
                }
            }
            ensure!(
                started.elapsed() < Duration::from_secs(8),
                "CAPTURE_TIMEOUT"
            );
            thread::sleep(Duration::from_millis(10));
        }
    }
}
impl Drop for Capture {
    fn drop(&mut self) {
        self.stop.store(true, Ordering::Release);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}
fn write_png(path: &Path, width: u32, height: u32, pixels: &[u8]) -> Result<()> {
    let file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .mode(0o600)
        .open(path)?;
    let mut encoder = png::Encoder::new(BufWriter::new(file), width, height);
    encoder.set_color(png::ColorType::Rgb);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder.write_header()?;
    writer.write_image_data(pixels)?;
    writer.finish()?;
    Ok(())
}
fn run(fd: OwnedFd, node: u32, shared: Arc<Mutex<Shared>>, stop: Arc<AtomicBool>) -> Result<()> {
    pw::init();
    let mainloop = pw::main_loop::MainLoopRc::new(None)?;
    let context = pw::context::ContextRc::new(&mainloop, None)?;
    let core = context.connect_fd_rc(fd, None)?;
    let stream = pw::stream::StreamBox::new(
        &core,
        "wayfire-computer-use",
        properties! {*pw::keys::MEDIA_TYPE=>"Video",*pw::keys::MEDIA_CATEGORY=>"Capture",*pw::keys::MEDIA_ROLE=>"Screen"},
    )?;
    let data = Data {
        format: Default::default(),
        shared: shared.clone(),
    };
    let _listener = stream
        .add_local_listener_with_user_data(data)
        .state_changed(|_, data, _, new| {
            if let pw::stream::StreamState::Error(detail) = new {
                let detail: String = detail
                    .chars()
                    .filter(|c| !c.is_control())
                    .take(512)
                    .collect();
                data.shared.lock().unwrap().error =
                    Some(format!("PIPEWIRE_STREAM_ERROR: {detail}"));
            }
        })
        .param_changed(|_, data, id, param| {
            if id == spa::param::ParamType::Format.as_raw() {
                if let Some(param) = param {
                    if data.format.parse(param).is_err() {
                        data.shared.lock().unwrap().error = Some("UNSUPPORTED_FRAME_FORMAT".into());
                    }
                }
            }
        })
        .process(|stream, data| {
            // SAFETY: the raw buffer comes from this stream and is returned to
            // it exactly once below. No pointers are retained after returning it.
            let raw = unsafe { stream.dequeue_raw_buffer() };
            if raw.is_null() {
                return;
            }
            let result = unsafe { copy_frame(raw, &data.format) };
            unsafe { stream.queue_raw_buffer(raw) };
            match result {
                Ok(frame) => data.shared.lock().unwrap().frame = Some(frame),
                Err(error) => data.shared.lock().unwrap().error = Some(error.to_string()),
            }
        })
        .register()?;
    let object = spa::pod::object!(
        spa::utils::SpaTypes::ObjectParamFormat,
        spa::param::ParamType::EnumFormat,
        spa::pod::property!(
            spa::param::format::FormatProperties::MediaType,
            Id,
            spa::param::format::MediaType::Video
        ),
        spa::pod::property!(
            spa::param::format::FormatProperties::MediaSubtype,
            Id,
            spa::param::format::MediaSubtype::Raw
        ),
        spa::pod::property!(
            spa::param::format::FormatProperties::VideoFormat,
            Choice,
            Enum,
            Id,
            spa::param::video::VideoFormat::BGRx,
            spa::param::video::VideoFormat::BGRx,
            spa::param::video::VideoFormat::BGRA,
            spa::param::video::VideoFormat::RGBx,
            spa::param::video::VideoFormat::RGBA
        ),
        spa::pod::property!(
            spa::param::format::FormatProperties::VideoSize,
            Choice,
            Range,
            Rectangle,
            spa::utils::Rectangle {
                width: 1920,
                height: 1080
            },
            spa::utils::Rectangle {
                width: 1,
                height: 1
            },
            spa::utils::Rectangle {
                width: 16384,
                height: 16384
            }
        ),
        spa::pod::property!(
            spa::param::format::FormatProperties::VideoFramerate,
            Choice,
            Range,
            Fraction,
            spa::utils::Fraction { num: 30, denom: 1 },
            spa::utils::Fraction { num: 0, denom: 1 },
            spa::utils::Fraction { num: 240, denom: 1 }
        )
    );
    let bytes = spa::pod::serialize::PodSerializer::serialize(
        std::io::Cursor::new(Vec::new()),
        &spa::pod::Value::Object(object),
    )?
    .0
    .into_inner();
    let mut params = [spa::pod::Pod::from_bytes(&bytes).context("PIPEWIRE_FORMAT_FAILED")?];
    stream.connect(
        spa::utils::Direction::Input,
        Some(node),
        pw::stream::StreamFlags::AUTOCONNECT | pw::stream::StreamFlags::MAP_BUFFERS,
        &mut params,
    )?;
    while !stop.load(Ordering::Acquire) {
        mainloop.loop_().iterate(Duration::from_millis(50));
    }
    stream.disconnect()?;
    Ok(())
}
unsafe fn copy_frame(
    raw: *mut pw::sys::pw_buffer,
    format: &spa::param::video::VideoInfoRaw,
) -> Result<Frame> {
    // SAFETY: caller owns a currently dequeued stream buffer. Each foreign
    // pointer/count and mapped-byte range is checked before dereferencing.
    let buffer = unsafe { (*raw).buffer };
    ensure!(!buffer.is_null(), "EMPTY_FRAME");
    let buffer = unsafe { &*buffer };
    ensure!(
        buffer.n_datas == 1 && !buffer.datas.is_null(),
        "UNSUPPORTED_FRAME_PLANES"
    );
    let data = unsafe { &*buffer.datas };
    ensure!(
        !data.data.is_null() && !data.chunk.is_null(),
        "UNMAPPED_FRAME"
    );
    let chunk = unsafe { &*data.chunk };
    let (width, height) = (format.size().width, format.size().height);
    ensure!(
        matches!(
            format.format(),
            spa::param::video::VideoFormat::BGRx
                | spa::param::video::VideoFormat::BGRA
                | spa::param::video::VideoFormat::RGBx
                | spa::param::video::VideoFormat::RGBA
        ) && width > 0
            && height > 0,
        "UNSUPPORTED_FRAME_FORMAT"
    );
    let row = usize::try_from(width)?
        .checked_mul(4)
        .context("FRAME_TOO_LARGE")?;
    let stride = usize::try_from(chunk.stride).context("UNSUPPORTED_FRAME_STRIDE")?;
    let length = stride
        .checked_mul(height as usize - 1)
        .and_then(|v| v.checked_add(row))
        .context("FRAME_TOO_LARGE")?;
    let offset = chunk.offset as usize;
    ensure!(
        stride >= row
            && length <= chunk.size as usize
            && offset
                .checked_add(length)
                .is_some_and(|n| n <= data.maxsize as usize),
        "INVALID_FRAME_RANGE"
    );
    let bytes = unsafe { std::slice::from_raw_parts(data.data.cast::<u8>().add(offset), length) };
    let mut pixels = Vec::with_capacity(width as usize * height as usize * 3);
    for y in 0..height as usize {
        for pixel in bytes[y * stride..y * stride + row].chunks_exact(4) {
            if matches!(
                format.format(),
                spa::param::video::VideoFormat::BGRx | spa::param::video::VideoFormat::BGRA
            ) {
                pixels.extend_from_slice(&[pixel[2], pixel[1], pixel[0]]);
            } else {
                pixels.extend_from_slice(&pixel[..3]);
            }
        }
    }
    let mut pts = None;
    if buffer.n_metas > 0 && !buffer.metas.is_null() {
        let metas = unsafe { std::slice::from_raw_parts(buffer.metas, buffer.n_metas as usize) };
        for meta in metas {
            if meta.type_ == spa::sys::SPA_META_Header
                && meta.size as usize >= std::mem::size_of::<spa::sys::spa_meta_header>()
                && !meta.data.is_null()
            {
                pts = Some(
                    unsafe {
                        std::ptr::read_unaligned(meta.data.cast::<spa::sys::spa_meta_header>())
                    }
                    .pts,
                );
            }
        }
    }
    Ok(Frame {
        width,
        height,
        pixels,
        received: Instant::now(),
        pts,
    })
}
