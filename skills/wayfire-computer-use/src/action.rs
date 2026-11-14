use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Point {
    pub x: i64,
    pub y: i64,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Button {
    Left,
    Right,
    Wheel,
    Middle,
    Back,
    Forward,
}
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case", deny_unknown_fields)]
pub enum Action {
    Screenshot {},
    Wait {},
    Move {
        x: i64,
        y: i64,
        #[serde(default)]
        keys: Option<Vec<String>>,
    },
    Click {
        x: i64,
        y: i64,
        button: Button,
        #[serde(default)]
        keys: Option<Vec<String>>,
    },
    DoubleClick {
        x: i64,
        y: i64,
        #[serde(default)]
        keys: Option<Vec<String>>,
    },
    Drag {
        path: Vec<Point>,
        #[serde(default)]
        keys: Option<Vec<String>>,
    },
    Scroll {
        x: i64,
        y: i64,
        scroll_x: i64,
        scroll_y: i64,
        #[serde(default)]
        keys: Option<Vec<String>>,
    },
    Keypress {
        keys: Vec<String>,
    },
    Type {
        text: String,
    },
}
impl Action {
    pub fn validate(&self) -> Result<()> {
        if let Self::Type { text } = self {
            ensure!(text.chars().count() <= 10_000, "INVALID_TEXT");
        }
        if let Self::Drag { path, .. } = self {
            ensure!((2..=1000).contains(&path.len()), "INVALID_PATH");
        }
        if let Some(keys) = self.keys() {
            ensure!(keys.iter().all(|key| !key.is_empty()), "INVALID_KEYS");
        }
        Ok(())
    }
    pub fn keys(&self) -> Option<&Vec<String>> {
        match self {
            Self::Move { keys, .. }
            | Self::Click { keys, .. }
            | Self::DoubleClick { keys, .. }
            | Self::Drag { keys, .. }
            | Self::Scroll { keys, .. } => keys.as_ref(),
            Self::Keypress { keys } => Some(keys),
            _ => None,
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_unknown_fields_and_boolean_coordinates() {
        for input in [
            r#"{"type":"screenshot","x":1}"#,
            r#"{"type":"move","x":true,"y":2}"#,
            r#"{"type":"type","text":"x","shell":"bad"}"#,
        ] {
            assert!(serde_json::from_str::<Action>(input).is_err());
        }
    }
    #[test]
    fn unicode_limit_counts_codepoints() {
        assert!(
            Action::Type {
                text: "你".repeat(10_000)
            }
            .validate()
            .is_ok()
        );
        assert!(
            Action::Type {
                text: "你".repeat(10_001)
            }
            .validate()
            .is_err()
        );
    }
    #[test]
    fn rejects_short_drag() {
        assert!(
            Action::Drag {
                path: vec![],
                keys: None
            }
            .validate()
            .is_err()
        );
    }
}
