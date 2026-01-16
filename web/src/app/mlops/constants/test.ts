export const meta_data = `
{
  format: YOLO,
  classes: [person, car, dog, cat],
  num_classes: 4,
  num_images: 150,
  labels: {
    img001.jpg: [
      {
        class_id: 0,
        class_name: person,
        x_center: 0.512345,
        y_center: 0.623456,
        width: 0.234567,
        height: 0.345678
      }
    ],
    img002.jpg: [
      {
        class_id: 2,
        class_name: dog,
        x_center: 0.712345,
        y_center: 0.523456,
        width: 0.334567,
        height: 0.445678
      }
    ]
  },
  statistics: {
    total_annotations: 320,
    images_with_annotations: 145,
    images_without_annotations: 5,
    class_distribution: {
      person: 120,
      car: 95,
      dog: 75,
      cat: 30
    }
  }
}
`