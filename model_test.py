import tensorflow as tf

model = tf.keras.models.load_model(
    "IDP_Fall_Detection/fall_model.keras"
)

model.summary()