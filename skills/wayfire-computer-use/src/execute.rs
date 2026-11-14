use crate::{
    action::{Action, Button, Point},
    desktop::Input,
};
use anyhow::{Result, bail, ensure};
use std::{
    sync::atomic::{AtomicBool, Ordering},
    time::{Duration, Instant},
};

pub fn key(name: &str) -> Result<(u32, u32)> {
    let name = name.to_ascii_uppercase();
    let pair = match name.as_str() {
        "CTRL" | "CONTROL" => (29, 4),
        "SHIFT" => (42, 1),
        "ALT" => (56, 8),
        "SUPER" | "META" => (125, 64),
        "ENTER" | "RETURN" => (28, 0),
        "TAB" => (15, 0),
        "ESC" | "ESCAPE" => (1, 0),
        "BACKSPACE" => (14, 0),
        "DELETE" => (111, 0),
        "LEFT" | "ARROWLEFT" => (105, 0),
        "RIGHT" | "ARROWRIGHT" => (106, 0),
        "UP" | "ARROWUP" => (103, 0),
        "DOWN" | "ARROWDOWN" => (108, 0),
        "HOME" => (102, 0),
        "END" => (107, 0),
        "PAGEUP" => (104, 0),
        "PAGEDOWN" => (109, 0),
        "SPACE" => (57, 0),
        _ => {
            for (letters, start) in [
                ("QWERTYUIOP", 16),
                ("ASDFGHJKL", 30),
                ("ZXCVBNM", 44),
                ("1234567890", 2),
            ] {
                if name.len() == 1
                    && let Some(index) = letters.find(&name)
                {
                    return Ok((start + index as u32, 0));
                }
            }
            if let Some(number) = name.strip_prefix('F').and_then(|n| n.parse::<u32>().ok())
                && (1..=12).contains(&number)
            {
                return Ok((
                    if number <= 10 {
                        58 + number
                    } else {
                        76 + number
                    },
                    0,
                ));
            }
            bail!("UNSUPPORTED_KEY")
        }
    };
    Ok(pair)
}
#[derive(Debug, PartialEq)]
enum Character {
    Key(u32, u32),
    Unicode(char),
}
fn character(c: char) -> Result<Character> {
    let special = match c {
        '\n' => Some(28),
        '\t' => Some(15),
        ' ' => Some(57),
        _ => None,
    };
    if let Some(code) = special {
        return Ok(Character::Key(code, 0));
    }
    if c.is_ascii_alphanumeric() {
        let (code, _) = key(&c.to_string())?;
        return Ok(Character::Key(code, u32::from(c.is_ascii_uppercase())));
    }
    let codes = [12, 13, 26, 27, 39, 40, 41, 51, 52, 53, 43];
    for (chars, mask) in [("-=[];'`,./\\", 0), ("_+{}:\"~<>?|", 1)] {
        if let Some(index) = chars.chars().position(|v| v == c) {
            return Ok(Character::Key(codes[index], mask));
        }
    }
    if let Some(index) = "!@#$%^&*()".chars().position(|v| v == c) {
        return Ok(Character::Key(2 + index as u32, 1));
    }
    ensure!(!c.is_control(), "UNSUPPORTED_UNICODE");
    Ok(Character::Unicode(c))
}
fn active(cancel: &AtomicBool, deadline: Instant) -> Result<()> {
    ensure!(!cancel.load(Ordering::Acquire), "ACTION_CANCELLED");
    ensure!(Instant::now() < deadline, "ACTION_TIMEOUT");
    Ok(())
}
fn sleep(duration: Duration, cancel: &AtomicBool, deadline: Instant) -> Result<()> {
    let end = Instant::now() + duration;
    while Instant::now() < end {
        active(cancel, deadline)?;
        std::thread::sleep(Duration::from_millis(5));
    }
    Ok(())
}
pub fn execute(
    input: &mut Input,
    action: &Action,
    width: u32,
    height: u32,
    cancel: &AtomicBool,
) -> Result<()> {
    action.validate()?;
    let points = match action {
        Action::Move { x, y, .. }
        | Action::Click { x, y, .. }
        | Action::DoubleClick { x, y, .. }
        | Action::Scroll { x, y, .. } => vec![Point { x: *x, y: *y }],
        Action::Drag { path, .. } => path.clone(),
        _ => vec![],
    };
    for point in &points {
        ensure!(
            point.x >= 0
                && point.y >= 0
                && point.x < i64::from(width)
                && point.y < i64::from(height),
            "COORDINATE_OUT_OF_BOUNDS"
        );
    }
    let keys: Vec<_> = action
        .keys()
        .into_iter()
        .flatten()
        .map(|k| key(k))
        .collect::<Result<_>>()?;
    let chars = match action {
        Action::Type { text } => text.chars().map(character).collect::<Result<Vec<_>>>()?,
        _ => vec![],
    };
    let deadline = Instant::now() + Duration::from_secs(30);
    let result = (|| {
        active(cancel, deadline)?;
        let mut mask = 0;
        for (code, modifier) in keys {
            active(cancel, deadline)?;
            input.key(code, true)?;
            mask |= modifier;
            input.modifiers(mask)?;
        }
        match action {
            Action::Screenshot {} | Action::Keypress { .. } => {}
            Action::Wait {} => sleep(Duration::from_millis(250), cancel, deadline)?,
            Action::Type { .. } => {
                for c in chars {
                    active(cancel, deadline)?;
                    match c {
                        Character::Unicode(c) => input.unicode(c)?,
                        Character::Key(code, mask) => {
                            // Activate this keyboard before setting Shift. A
                            // compositor can switch keyboards on the first key
                            // event and replace modifiers sent before that event.
                            if mask != 0 {
                                input.key(42, true)?;
                            }
                            input.modifiers(mask)?;
                            sleep(Duration::from_millis(50), cancel, deadline)?;
                            input.key(code, true)?;
                            input.key(code, false)?;
                            // A Wayland roundtrip acknowledges the compositor,
                            // not an input-method relay or the focused client.
                            // Keep this character's modifiers stable while it
                            // is delivered before beginning the next character.
                            sleep(Duration::from_millis(50), cancel, deadline)?;
                            if mask != 0 {
                                input.key(42, false)?;
                            }
                            input.modifiers(0)?;
                        }
                    }
                }
            }
            Action::Drag { path, .. } => {
                input.motion(path[0].x as u32, path[0].y as u32, width, height)?;
                input.button(272, true)?;
                for point in &path[1..] {
                    active(cancel, deadline)?;
                    input.motion(point.x as u32, point.y as u32, width, height)?;
                    sleep(Duration::from_millis(10), cancel, deadline)?;
                }
                input.button(272, false)?;
            }
            _ => {
                input.motion(points[0].x as u32, points[0].y as u32, width, height)?;
                match action {
                    Action::Click { button, .. } => {
                        let code = match button {
                            Button::Left => 272,
                            Button::Right => 273,
                            Button::Wheel | Button::Middle => 274,
                            Button::Back => 275,
                            Button::Forward => 276,
                        };
                        input.button(code, true)?;
                        input.button(code, false)?;
                    }
                    Action::DoubleClick { .. } => {
                        for _ in 0..2 {
                            active(cancel, deadline)?;
                            input.button(272, true)?;
                            input.button(272, false)?;
                            sleep(Duration::from_millis(60), cancel, deadline)?;
                        }
                    }
                    Action::Scroll {
                        scroll_x, scroll_y, ..
                    } => {
                        if *scroll_y != 0 {
                            input.axis(false, *scroll_y as f64 / 10.)?;
                        }
                        if *scroll_x != 0 {
                            input.axis(true, *scroll_x as f64 / 10.)?;
                        }
                    }
                    _ => {}
                }
            }
        };
        Ok(())
    })();
    let release = input.release();
    match (result, release) {
        (Err(error), _) => Err(error),
        (Ok(()), Err(error)) => Err(error),
        (Ok(()), Ok(())) => {
            std::thread::sleep(Duration::from_millis(50));
            Ok(())
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn aliases_and_function_keys() {
        assert_eq!(key("CONTROL").unwrap(), (29, 4));
        assert_eq!(key("F11").unwrap(), (87, 0));
        assert_eq!(key("F12").unwrap(), (88, 0));
        assert!(key("CMD").is_err());
        assert!(key("F13").is_err());
    }
    #[test]
    fn characters_preserve_text_semantics() {
        assert_eq!(character('A').unwrap(), Character::Key(30, 1));
        assert_eq!(character('!').unwrap(), Character::Key(2, 1));
        assert_eq!(character('你').unwrap(), Character::Unicode('你'));
        assert!(character('\0').is_err());
    }
}
